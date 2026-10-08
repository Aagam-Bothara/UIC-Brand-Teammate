# Prompt Validation Script
# Tests that all prompt templates exist and have required content

Write-Host "=" -ForegroundColor Blue -NoNewline; Write-Host ("=" * 59) -ForegroundColor Blue
Write-Host "UIC Editorial Assistant - Prompt Validation" -ForegroundColor Cyan
Write-Host "Task 3.2: Prompt Engineering" -ForegroundColor Cyan
Write-Host "=" -ForegroundColor Blue -NoNewline; Write-Host ("=" * 59) -ForegroundColor Blue
Write-Host ""

$allPassed = $true
$promptsDir = $PSScriptRoot

# Test 1: Check files exist
Write-Host "TEST 1: Checking prompt files exist" -ForegroundColor Yellow
Write-Host ("-" * 60)

$requiredFiles = @(
    "system_prompt.txt",
    "rewrite_prompt_template.txt",
    "detection_prompt_template.txt"
)

foreach ($file in $requiredFiles) {
    $path = Join-Path $promptsDir $file
    if (Test-Path $path) {
        $size = (Get-Item $path).Length
        Write-Host "✅ $file exists ($size bytes)" -ForegroundColor Green
    } else {
        Write-Host "❌ $file NOT FOUND" -ForegroundColor Red
        $allPassed = $false
    }
}
Write-Host ""

# Test 2: Validate system prompt
Write-Host "TEST 2: Validating system_prompt.txt" -ForegroundColor Yellow
Write-Host ("-" * 60)

$systemPromptPath = Join-Path $promptsDir "system_prompt.txt"
if (Test-Path $systemPromptPath) {
    $content = Get-Content $systemPromptPath -Raw
    
    $requiredSections = @(
        "Your Responsibilities",
        "UIC Brand Guidelines",
        "Key Audiences",
        "Communication Channels",
        "Your Approach",
        "Output Requirements"
    )
    
    $missingSections = @()
    foreach ($section in $requiredSections) {
        if ($content -notmatch [regex]::Escape($section)) {
            $missingSections += $section
        }
    }
    
    if ($missingSections.Count -gt 0) {
        Write-Host "❌ Missing sections: $($missingSections -join ', ')" -ForegroundColor Red
        $allPassed = $false
    } else {
        Write-Host "✅ All required sections present" -ForegroundColor Green
    }
    
    $keyConcepts = @(
        "brand compliance",
        "accessibility",
        "audience",
        "University of Illinois Chicago",
        "reading level"
    )
    
    $missingConcepts = @()
    foreach ($concept in $keyConcepts) {
        if ($content -notmatch [regex]::Escape($concept)) {
            $missingConcepts += $concept
        }
    }
    
    if ($missingConcepts.Count -gt 0) {
        Write-Host "⚠️  Missing key concepts: $($missingConcepts -join ', ')" -ForegroundColor Yellow
    } else {
        Write-Host "✅ All key concepts mentioned" -ForegroundColor Green
    }
    
    Write-Host "✅ System prompt is $($content.Length) characters" -ForegroundColor Green
} else {
    Write-Host "❌ System prompt file not found" -ForegroundColor Red
    $allPassed = $false
}
Write-Host ""

# Test 3: Validate detection template
Write-Host "TEST 3: Validating detection_prompt_template.txt" -ForegroundColor Yellow
Write-Host ("-" * 60)

$detectionPath = Join-Path $promptsDir "detection_prompt_template.txt"
if (Test-Path $detectionPath) {
    $content = Get-Content $detectionPath -Raw
    
    $requiredPlaceholders = @(
        "{audience}",
        "{channel}",
        "{reading_level_target}",
        "{text_to_analyze}",
        "{guidelines_context}"
    )
    
    $missingPlaceholders = @()
    foreach ($placeholder in $requiredPlaceholders) {
        if ($content -notmatch [regex]::Escape($placeholder)) {
            $missingPlaceholders += $placeholder
        }
    }
    
    if ($missingPlaceholders.Count -gt 0) {
        Write-Host "❌ Missing placeholders: $($missingPlaceholders -join ', ')" -ForegroundColor Red
        $allPassed = $false
    } else {
        Write-Host "✅ All required placeholders present" -ForegroundColor Green
    }
    
    if ($content -match "JSON" -or $content -match "json") {
        Write-Host "✅ Specifies JSON output format" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Does not specify JSON output format" -ForegroundColor Yellow
    }
    
    Write-Host "✅ Detection template is $($content.Length) characters" -ForegroundColor Green
} else {
    Write-Host "❌ Detection template file not found" -ForegroundColor Red
    $allPassed = $false
}
Write-Host ""

# Test 4: Validate rewrite template
Write-Host "TEST 4: Validating rewrite_prompt_template.txt" -ForegroundColor Yellow
Write-Host ("-" * 60)

$rewritePath = Join-Path $promptsDir "rewrite_prompt_template.txt"
if (Test-Path $rewritePath) {
    $content = Get-Content $rewritePath -Raw
    
    $requiredPlaceholders = @(
        "{audience}",
        "{channel}",
        "{reading_level_target}",
        "{original_text}",
        "{issues_list}",
        "{guidelines_context}"
    )
    
    $missingPlaceholders = @()
    foreach ($placeholder in $requiredPlaceholders) {
        if ($content -notmatch [regex]::Escape($placeholder)) {
            $missingPlaceholders += $placeholder
        }
    }
    
    if ($missingPlaceholders.Count -gt 0) {
        Write-Host "❌ Missing placeholders: $($missingPlaceholders -join ', ')" -ForegroundColor Red
        $allPassed = $false
    } else {
        Write-Host "✅ All required placeholders present" -ForegroundColor Green
    }
    
    $tagTypes = @("[BRAND]", "[ACCESSIBILITY]", "[CONTENT]", "[READING_LEVEL]", "[AUDIENCE_TONE]")
    $tagsMentioned = 0
    foreach ($tag in $tagTypes) {
        if ($content -match [regex]::Escape($tag)) {
            $tagsMentioned++
        }
    }
    
    if ($tagsMentioned -ge 4) {
        Write-Host "✅ Mentions $tagsMentioned/5 tag types" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Only mentions $tagsMentioned/5 tag types" -ForegroundColor Yellow
    }
    
    Write-Host "✅ Rewrite template is $($content.Length) characters" -ForegroundColor Green
} else {
    Write-Host "❌ Rewrite template file not found" -ForegroundColor Red
    $allPassed = $false
}
Write-Host ""

# Test 5: Consistency check
Write-Host "TEST 5: Checking consistency across prompts" -ForegroundColor Yellow
Write-Host ("-" * 60)

$allContent = ""
foreach ($file in $requiredFiles) {
    $path = Join-Path $promptsDir $file
    if (Test-Path $path) {
        $allContent += Get-Content $path -Raw
    }
}

$rulesets = @("BRAND", "ACCESSIBILITY", "CONTENT", "READING_LEVEL", "AUDIENCE_TONE")
foreach ($file in $requiredFiles) {
    $path = Join-Path $promptsDir $file
    if (Test-Path $path) {
        $content = Get-Content $path -Raw
        $mentioned = 0
        foreach ($ruleset in $rulesets) {
            if ($content -match $ruleset) {
                $mentioned++
            }
        }
        if ($mentioned -ge 4) {
            Write-Host "✅ $file mentions $mentioned/5 rulesets" -ForegroundColor Green
        } else {
            Write-Host "⚠️  $file only mentions $mentioned/5 rulesets" -ForegroundColor Yellow
        }
    }
}

Write-Host ""

# Summary
Write-Host "=" -ForegroundColor Blue -NoNewline; Write-Host ("=" * 59) -ForegroundColor Blue
Write-Host "TEST SUMMARY" -ForegroundColor Cyan
Write-Host "=" -ForegroundColor Blue -NoNewline; Write-Host ("=" * 59) -ForegroundColor Blue
Write-Host ""

if ($allPassed) {
    Write-Host "🎉 All tests passed! Prompts are ready for integration." -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. Review prompts for content accuracy"
    Write-Host "2. Test with actual Bedrock models (requires Task 3.1)"
    Write-Host "3. Proceed to Task 3.3: LLM Service Implementation"
    exit 0
} else {
    Write-Host "⚠️  Some tests failed. Please review and fix the issues above." -ForegroundColor Red
    exit 1
}
