"""
LLM Service for UIC Editorial Assistant
Task 3.3: LLM Service Implementation

This service handles all interactions with AWS Bedrock models (Claude Haiku and Sonnet)
for text rewriting, issue detection, and refinement operations.
"""

import json
import logging
import os
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .refinement import RefinementHandler


@dataclass
class LLMResponse:
    """Response from LLM invocation."""
    text: str
    model_id: str
    latency_ms: float
    token_usage: Optional[Dict[str, int]] = None
    selection: Optional[Dict[str, Any]] = None
    estimated_cost_usd: Optional[float] = None
    estimated_savings_usd: Optional[float] = None
    refinement: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            'text_length': len(self.text),
            'model_id': self.model_id,
            'latency_ms': self.latency_ms,
            'token_usage': self.token_usage,
            'selection': self.selection,
            'estimated_cost_usd': self.estimated_cost_usd,
            'estimated_savings_usd': self.estimated_savings_usd,
            'refinement': self.refinement
        }


@dataclass(frozen=True)
class ModelSelectionDecision:
    """Explainable result of adaptive model selection."""
    model_id: str
    model_name: str
    complexity_score: float
    reason: str
    metrics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable decision for logs and API metadata."""
        return asdict(self)


class LLMServiceError(Exception):
    """Base exception for LLM Service errors."""
    pass


class PromptLoadError(LLMServiceError):
    """Raised when prompt templates cannot be loaded."""
    pass


class ModelInvocationError(LLMServiceError):
    """Raised when model invocation fails."""
    pass


class LLMService:
    """
    Service for interacting with AWS Bedrock LLM models.
    
    Handles:
    - Loading and formatting prompt templates
    - Model selection (Haiku vs Sonnet based on complexity)
    - Retry logic with exponential backoff
    - Error handling for all failure modes
    - CloudWatch logging
    
    Public Methods:
        rewrite_text() - Generate improved text with change tags
        detect_issues() - Analyze text for compliance issues (JSON output)
        refine_text() - Apply user-requested refinements
    """
    
    # Model IDs - updated to latest versions from test_bedrock_setup.py
    HAIKU_MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"
    SONNET_MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    
    # Configuration
    REGION = "us-east-1"
    CONNECTION_TIMEOUT = 30
    READ_TIMEOUT = 120
    MAX_RETRIES = 3
    BASE_DELAY = 1.0  # seconds for exponential backoff
    
    # Model selection thresholds
    WORD_COUNT_THRESHOLD = 500  # Use Sonnet if > 500 words
    COMPLEXITY_SCORE_THRESHOLD = 50.0

    # USD per one million tokens; configurable without a deployment.
    HAIKU_INPUT_COST_PER_MILLION = 0.25
    HAIKU_OUTPUT_COST_PER_MILLION = 1.25
    SONNET_INPUT_COST_PER_MILLION = 3.00
    SONNET_OUTPUT_COST_PER_MILLION = 15.00
    
    def __init__(self, bedrock_client: Optional[Any] = None):
        """
        Initialize LLM Service.
        
        Args:
            bedrock_client: Optional pre-configured boto3 bedrock-runtime client.
                           If None, creates a new client.
        """
        self.logger = self._setup_logging()
        self.logger.info("Initializing LLMService")
        self._cost_lock = threading.Lock()
        self._cost_metrics = {
            'requests_with_usage': 0,
            'haiku_requests': 0,
            'sonnet_requests': 0,
            'actual_cost_usd': 0.0,
            'sonnet_baseline_cost_usd': 0.0,
            'estimated_savings_usd': 0.0,
        }
        self._pricing = self._load_pricing()
        self.refinement_handler = RefinementHandler()
        
        # Initialize Bedrock client
        if bedrock_client:
            self.bedrock_client = bedrock_client
            self.logger.info("Using provided Bedrock client")
        else:
            self.bedrock_client = self._create_bedrock_client()
            self.logger.info(f"Created new Bedrock client (region: {self.REGION})")
        
        # Load prompt templates
        try:
            self.system_prompt = self._load_prompt_template("system_prompt.txt")
            self.rewrite_template = self._load_prompt_template("rewrite_prompt_template.txt")
            self.detection_template = self._load_prompt_template("detection_prompt_template.txt")
            self.logger.info("All prompt templates loaded successfully")
        except PromptLoadError as e:
            self.logger.error(f"Failed to load prompt templates: {e}")
            raise
    
    def rewrite_text(
        self,
        original_text: str,
        issues: List[Dict[str, Any]],
        guidelines: List[Dict[str, str]],
        audience: str,
        channel: str
    ) -> LLMResponse:
        """
        Generate improved text with inline change tags.
        
        Args:
            original_text: Original text to rewrite
            issues: List of detected issues from rule engine
            guidelines: Retrieved guidelines from RAG service
            audience: Target audience (Students, Faculty, Staff)
            channel: Communication channel (Email, Website, Social Media)
        
        Returns:
            LLMResponse with rewritten text containing change tags
        
        Raises:
            ModelInvocationError: If model invocation fails after retries
        """
        self.logger.info(
            f"Starting text rewrite (audience: {audience}, channel: {channel}, "
            f"text_length: {len(original_text)}, issues: {len(issues)})"
        )
        
        # Determine reading level based on audience
        reading_level = self._get_reading_level(audience)
        
        # Format issues and guidelines
        issues_text = self._format_issues(issues)
        guidelines_text = self._format_guidelines(guidelines)
        
        # Fill template with actual values
        user_prompt = self.rewrite_template.format(
            audience=audience,
            channel=channel,
            reading_level_target=reading_level,
            original_text=original_text,
            issues_list=issues_text,
            guidelines_context=guidelines_text
        )
        
        # Select appropriate model
        decision = self.select_model(original_text, issues=issues, task="rewrite")
        model_id = decision.model_id
        
        # Invoke model with retry logic
        response = self._invoke_model_with_retry(
            model_id=model_id,
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            max_tokens=4000,
            temperature=0.5
        )
        response.selection = decision.to_dict()
        
        self.logger.info(
            f"Text rewrite completed (model: {model_id}, "
            f"latency: {response.latency_ms:.0f}ms)"
        )
        
        return response
    
    def detect_issues(
        self,
        text_to_analyze: str,
        guidelines: List[Dict[str, str]],
        audience: str,
        channel: str
    ) -> List[Dict[str, Any]]:
        """
        Analyze text to detect compliance issues.
        
        This is an optional step that can complement or validate rule engine output.
        
        Args:
            text_to_analyze: Text to analyze
            guidelines: Retrieved guidelines from RAG service
            audience: Target audience
            channel: Communication channel
        
        Returns:
            List of detected issues in JSON format
        
        Raises:
            ModelInvocationError: If model invocation fails after retries
        """
        self.logger.info(
            f"Starting issue detection (audience: {audience}, channel: {channel}, "
            f"text_length: {len(text_to_analyze)})"
        )
        
        # Determine reading level based on audience
        reading_level = self._get_reading_level(audience)
        
        # Format guidelines
        guidelines_text = self._format_guidelines(guidelines)
        
        # Fill template
        user_prompt = self.detection_template.format(
            audience=audience,
            channel=channel,
            reading_level_target=reading_level,
            text_to_analyze=text_to_analyze,
            guidelines_context=guidelines_text
        )
        
        decision = self.select_model(text_to_analyze, task="detection")
        model_id = decision.model_id
        
        # Invoke model
        response = self._invoke_model_with_retry(
            model_id=model_id,
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            max_tokens=2000,
            temperature=0.3  # Lower temperature for more consistent JSON
        )
        response.selection = decision.to_dict()
        
        # Parse JSON response
        try:
            issues = json.loads(response.text)
            self.logger.info(f"Issue detection completed (issues found: {len(issues)})")
            return issues
        except json.JSONDecodeError as e:
            self.logger.warning(f"Failed to parse JSON response: {e}")
            # Return empty list on parse failure
            return []
    
    def refine_text(
        self,
        current_text: str,
        refinement_request: str,
        audience: str,
        channel: str,
        context: Optional[str] = None,
        selection_start: Optional[int] = None,
        selection_end: Optional[int] = None
    ) -> LLMResponse:
        """
        Apply user-requested refinements to text.
        
        This handles chat-based interactions where users ask for specific changes.
        
        Args:
            current_text: Current version of the text
            refinement_request: User's refinement request
            audience: Target audience
            channel: Communication channel
            context: Optional additional factual context
            selection_start: Optional inclusive character offset for selected text
            selection_end: Optional exclusive character offset for selected text
        
        Returns:
            LLMResponse with refined text
        
        Raises:
            ModelInvocationError: If model invocation fails after retries
        """
        plan = self.refinement_handler.plan(
            current_text, refinement_request, selection_start, selection_end
        )
        self.logger.info(
            f"Starting text refinement (audience: {audience}, channel: {channel}, "
            f"request: {refinement_request[:100]}...)"
        )
        
        user_prompt = self.refinement_handler.build_prompt(
            current_text, plan, audience, channel,
            self._get_reading_level(audience), context
        )

        decision = self.select_model(
            current_text,
            refinement_request=refinement_request,
            task="refinement"
        )
        model_id = decision.model_id
        
        # Invoke model
        response = self._invoke_model_with_retry(
            model_id=model_id,
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            max_tokens=4000,
            temperature=0.5
        )
        response.text = self.refinement_handler.merge_response(
            current_text, response.text, plan
        )
        response.selection = decision.to_dict()
        response.refinement = plan.to_dict()
        
        self.logger.info(
            f"Text refinement completed (model: {model_id}, "
            f"latency: {response.latency_ms:.0f}ms)"
        )
        
        return response
    
    # Private methods
    
    def _setup_logging(self) -> logging.Logger:
        """Configure CloudWatch-compatible structured logging."""
        logger = logging.getLogger(__name__)
        
        # Only configure if not already configured
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        
        return logger
    
    def _create_bedrock_client(self) -> Any:
        """Create boto3 bedrock-runtime client with proper configuration."""
        bedrock_config = Config(
            region_name=self.REGION,
            connect_timeout=self.CONNECTION_TIMEOUT,
            read_timeout=self.READ_TIMEOUT,
            retries={'max_attempts': self.MAX_RETRIES, 'mode': 'standard'}
        )
        
        return boto3.client('bedrock-runtime', config=bedrock_config)
    
    def _load_prompt_template(self, filename: str) -> str:
        """
        Load a prompt template file.
        
        Args:
            filename: Name of template file in backend/prompts/
        
        Returns:
            Template content as string
        
        Raises:
            PromptLoadError: If file cannot be loaded
        """
        # Determine prompts directory path
        # This works both from project root and from backend/ directory
        current_dir = Path(__file__).parent.parent
        prompts_dir = current_dir / "prompts"
        
        template_path = prompts_dir / filename
        
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.logger.debug(f"Loaded template: {filename} ({len(content)} bytes)")
            return content
        
        except FileNotFoundError:
            raise PromptLoadError(
                f"Template file not found: {template_path}. "
                f"Ensure prompts are in {prompts_dir}"
            )
        except Exception as e:
            raise PromptLoadError(f"Failed to load template {filename}: {e}")
    
    def _get_reading_level(self, audience: str) -> str:
        """
        Determine target reading level based on audience.
        
        Args:
            audience: Target audience (Students, Faculty, Staff)
        
        Returns:
            Reading level string (e.g., "Grade 8")
        """
        # From SPEC.md requirements
        if audience.lower() == "students":
            return "Grade 8"
        else:  # Faculty or Staff
            return "Grade 10"
    
    def _format_issues(self, issues: List[Dict[str, Any]]) -> str:
        """
        Format issues list as human-readable text for prompt.
        
        Args:
            issues: List of issue dictionaries
        
        Returns:
            Formatted issues as text
        """
        if not issues:
            return "No specific issues detected by automated rule checking."
        
        formatted = []
        for issue in issues:
            issue_type = issue.get('type', 'UNKNOWN')
            severity = issue.get('severity', 'medium')
            description = issue.get('description', 'No description')
            location = issue.get('location', '')
            
            formatted.append(
                f"- [{issue_type.upper()} - {severity.capitalize()}] {description}"
            )
            if location:
                formatted.append(f"  Location: \"{location}\"")
        
        return "\n".join(formatted)
    
    def _format_guidelines(self, guidelines: List[Dict[str, str]]) -> str:
        """
        Format guidelines as human-readable text for prompt.
        
        Args:
            guidelines: List of guideline dictionaries with 'text' and 'source_url'
        
        Returns:
            Formatted guidelines as text
        """
        if not guidelines:
            return "No specific guidelines retrieved."
        
        formatted = []
        for guideline in guidelines:
            text = guideline.get('text', '')
            source_url = guideline.get('source_url', '')
            
            if text:
                formatted.append(f"- {text}")
                if source_url:
                    formatted.append(f"  Source: {source_url}")
        
        return "\n".join(formatted)
    
    def calculate_complexity_score(
        self,
        text: str,
        issues: Optional[List[Dict[str, Any]]] = None,
        refinement_request: Optional[str] = None
    ) -> Tuple[float, Dict[str, Any]]:
        """Calculate a deterministic 0-100 document complexity score.

        The score balances document length (45 points), sentence complexity
        (20), vocabulary complexity (15), detected issue burden (15), and a
        multi-step refinement request (5). It uses inexpensive local heuristics,
        so selection never requires another model call.
        """
        if not isinstance(text, str):
            raise TypeError("text must be a string")

        words = re.findall(r"\b[\w'-]+\b", text, flags=re.UNICODE)
        sentences = [part for part in re.split(r"[.!?]+", text) if part.strip()]
        word_count = len(words)
        sentence_count = max(len(sentences), 1)
        average_sentence_length = word_count / sentence_count
        long_word_count = sum(1 for word in words if len(word.strip("'-")) >= 8)
        long_word_ratio = long_word_count / max(word_count, 1)

        issue_list = issues or []
        severity_weights = {'low': 0.5, 'medium': 1.0, 'high': 2.0, 'critical': 3.0}
        issue_weight = sum(
            severity_weights.get(str(issue.get('severity', 'medium')).lower(), 1.0)
            for issue in issue_list
        )

        request = refinement_request or ""
        request_words = re.findall(r"\b[\w'-]+\b", request, flags=re.UNICODE)
        multi_step_markers = len(re.findall(
            r"\b(?:and|also|then|while|but|except|preserve|compare|restructure)\b",
            request,
            flags=re.IGNORECASE
        ))
        request_complexity = min(
            1.0,
            (len(request_words) / 40.0) + (multi_step_markers / 4.0)
        )

        components = {
            'length': min(word_count / self.WORD_COUNT_THRESHOLD, 1.0) * 45.0,
            'sentence_complexity': min(average_sentence_length / 30.0, 1.0) * 20.0,
            'vocabulary_complexity': min(long_word_ratio / 0.30, 1.0) * 15.0,
            'issue_burden': min(issue_weight / 10.0, 1.0) * 15.0,
            'refinement_complexity': request_complexity * 5.0,
        }
        score = round(min(sum(components.values()), 100.0), 2)
        metrics = {
            'word_count': word_count,
            'sentence_count': len(sentences),
            'average_sentence_length': round(average_sentence_length, 2),
            'long_word_ratio': round(long_word_ratio, 4),
            'issue_count': len(issue_list),
            'weighted_issue_count': round(issue_weight, 2),
            'components': {name: round(value, 2) for name, value in components.items()},
        }
        return score, metrics

    def select_model(
        self,
        text: str,
        issues: Optional[List[Dict[str, Any]]] = None,
        refinement_request: Optional[str] = None,
        task: str = "general"
    ) -> ModelSelectionDecision:
        """Select Haiku or Sonnet and return an explainable decision."""
        score, metrics = self.calculate_complexity_score(
            text,
            issues=issues,
            refinement_request=refinement_request
        )
        word_count = metrics['word_count']

        if word_count > self.WORD_COUNT_THRESHOLD:
            model_id = self.SONNET_MODEL_ID
            reason = f"word_count_above_{self.WORD_COUNT_THRESHOLD}"
        elif score >= self.COMPLEXITY_SCORE_THRESHOLD:
            model_id = self.SONNET_MODEL_ID
            reason = f"complexity_score_at_least_{self.COMPLEXITY_SCORE_THRESHOLD:g}"
        else:
            model_id = self.HAIKU_MODEL_ID
            reason = "simple_content_cost_optimized"

        decision = ModelSelectionDecision(
            model_id=model_id,
            model_name="sonnet" if model_id == self.SONNET_MODEL_ID else "haiku",
            complexity_score=score,
            reason=reason,
            metrics={**metrics, 'task': task}
        )
        self.logger.info(
            "model_selection %s",
            json.dumps(decision.to_dict(), sort_keys=True)
        )
        return decision

    def _select_model(self, text: str) -> str:
        """Return only the model ID for backward compatibility."""
        return self.select_model(text).model_id

    def _load_pricing(self) -> Dict[str, Dict[str, float]]:
        """Load configurable token rates used only for cost estimation."""
        def rate(name: str, default: float) -> float:
            try:
                value = float(os.getenv(name, str(default)))
                return value if value >= 0 else default
            except ValueError:
                self.logger.warning("Invalid %s; using default %.4f", name, default)
                return default

        return {
            self.HAIKU_MODEL_ID: {
                'input': rate(
                    'BEDROCK_HAIKU_INPUT_COST_PER_MILLION',
                    self.HAIKU_INPUT_COST_PER_MILLION
                ),
                'output': rate(
                    'BEDROCK_HAIKU_OUTPUT_COST_PER_MILLION',
                    self.HAIKU_OUTPUT_COST_PER_MILLION
                ),
            },
            self.SONNET_MODEL_ID: {
                'input': rate(
                    'BEDROCK_SONNET_INPUT_COST_PER_MILLION',
                    self.SONNET_INPUT_COST_PER_MILLION
                ),
                'output': rate(
                    'BEDROCK_SONNET_OUTPUT_COST_PER_MILLION',
                    self.SONNET_OUTPUT_COST_PER_MILLION
                ),
            },
        }

    def _estimate_cost(self, model_id: str, token_usage: Dict[str, int]) -> float:
        pricing = self._pricing.get(model_id, self._pricing[self.SONNET_MODEL_ID])
        return (
            max(int(token_usage.get('input_tokens', 0)), 0) * pricing['input']
            + max(int(token_usage.get('output_tokens', 0)), 0) * pricing['output']
        ) / 1_000_000

    def _record_cost(self, response: LLMResponse) -> None:
        """Attach request estimates and update Lambda-instance aggregate savings."""
        if not response.token_usage:
            return
        actual_cost = self._estimate_cost(response.model_id, response.token_usage)
        baseline_cost = self._estimate_cost(self.SONNET_MODEL_ID, response.token_usage)
        savings = max(baseline_cost - actual_cost, 0.0)
        response.estimated_cost_usd = round(actual_cost, 8)
        response.estimated_savings_usd = round(savings, 8)

        with self._cost_lock:
            self._cost_metrics['requests_with_usage'] += 1
            key = (
                'haiku_requests'
                if response.model_id == self.HAIKU_MODEL_ID
                else 'sonnet_requests'
            )
            self._cost_metrics[key] += 1
            self._cost_metrics['actual_cost_usd'] += actual_cost
            self._cost_metrics['sonnet_baseline_cost_usd'] += baseline_cost
            self._cost_metrics['estimated_savings_usd'] += savings

        self.logger.info(
            "model_cost %s",
            json.dumps({
                'model_id': response.model_id,
                'token_usage': response.token_usage,
                'estimated_cost_usd': response.estimated_cost_usd,
                'estimated_savings_usd': response.estimated_savings_usd,
                'baseline': 'all_sonnet',
            }, sort_keys=True)
        )

    def get_cost_metrics(self) -> Dict[str, Any]:
        """Return cost and savings estimates for this service instance."""
        with self._cost_lock:
            metrics = dict(self._cost_metrics)
        for key in (
            'actual_cost_usd',
            'sonnet_baseline_cost_usd',
            'estimated_savings_usd'
        ):
            metrics[key] = round(metrics[key], 8)
        baseline = metrics['sonnet_baseline_cost_usd']
        metrics['savings_percentage'] = round(
            (metrics['estimated_savings_usd'] / baseline * 100.0)
            if baseline else 0.0,
            2
        )
        metrics['pricing_usd_per_million_tokens'] = {
            'haiku': dict(self._pricing[self.HAIKU_MODEL_ID]),
            'sonnet': dict(self._pricing[self.SONNET_MODEL_ID]),
        }
        return metrics

    def _invoke_model_with_retry(
        self,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float
    ) -> LLMResponse:
        """
        Invoke Bedrock model with exponential backoff retry logic.
        
        Args:
            model_id: Model identifier
            system_prompt: System-level instructions
            user_prompt: User-specific prompt
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation (0.0-1.0)
        
        Returns:
            LLMResponse with model output
        
        Raises:
            ModelInvocationError: If all retries fail
        """
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]
        }
        
        for attempt in range(self.MAX_RETRIES):
            try:
                start_time = time.time()
                
                response = self.bedrock_client.invoke_model(
                    modelId=model_id,
                    body=json.dumps(request_body),
                    contentType="application/json",
                    accept="application/json"
                )
                
                latency_ms = (time.time() - start_time) * 1000
                
                # Parse response
                response_body = json.loads(response['body'].read())
                response_text = response_body['content'][0]['text']
                
                # Extract token usage if available
                token_usage = None
                if 'usage' in response_body:
                    token_usage = {
                        'input_tokens': response_body['usage'].get('input_tokens', 0),
                        'output_tokens': response_body['usage'].get('output_tokens', 0)
                    }
                
                self.logger.debug(
                    f"Model invocation successful (attempt: {attempt + 1}, "
                    f"latency: {latency_ms:.0f}ms, tokens: {token_usage})"
                )
                
                result = LLMResponse(
                    text=response_text,
                    model_id=model_id,
                    latency_ms=latency_ms,
                    token_usage=token_usage
                )
                self._record_cost(result)
                return result
            
            except ClientError as e:
                error_code = e.response['Error']['Code']
                error_message = e.response['Error']['Message']
                
                # Check if error is retryable
                is_retryable = error_code in [
                    'ThrottlingException',
                    'ProvisionedThroughputExceededException',
                    'TooManyRequestsException',
                    'ServiceUnavailableException'
                ]
                
                if is_retryable and attempt < self.MAX_RETRIES - 1:
                    # Calculate exponential backoff delay
                    delay = self.BASE_DELAY * (2 ** attempt)
                    
                    self.logger.warning(
                        f"Retryable error on attempt {attempt + 1}/{self.MAX_RETRIES}: "
                        f"{error_code} - {error_message}. "
                        f"Retrying in {delay}s..."
                    )
                    
                    time.sleep(delay)
                    continue
                else:
                    # Non-retryable error or exhausted retries
                    self.logger.error(
                        f"Model invocation failed: {error_code} - {error_message}"
                    )
                    
                    raise ModelInvocationError(
                        f"Failed to invoke model {model_id} after {attempt + 1} attempts: "
                        f"{error_code} - {error_message}"
                    )
            
            except Exception as e:
                # Unexpected error
                self.logger.error(f"Unexpected error invoking model: {e}")
                
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.BASE_DELAY * (2 ** attempt)
                    self.logger.warning(f"Retrying in {delay}s...")
                    time.sleep(delay)
                    continue
                else:
                    raise ModelInvocationError(
                        f"Unexpected error invoking model {model_id}: {e}"
                    )
        
        # Should never reach here, but just in case
        raise ModelInvocationError(f"Failed to invoke model {model_id} after {self.MAX_RETRIES} attempts")


# Convenience function for quick initialization
def create_llm_service(bedrock_client: Optional[Any] = None) -> LLMService:
    """
    Create and return a configured LLM Service instance.
    
    Args:
        bedrock_client: Optional pre-configured boto3 client
    
    Returns:
        Configured LLMService instance
    """
    return LLMService(bedrock_client=bedrock_client)
