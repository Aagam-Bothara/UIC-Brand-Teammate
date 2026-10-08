# Task 3.1: Bedrock Setup - README

## Overview

This implements Task 3.1 from Workstream 3 (LLM Integration & Rewrite Logic):
- Configure boto3 for bedrock-runtime
- Request model access (Haiku & Sonnet)
- Store model IDs in Parameter Store  
- Test connection with simple prompts

## Prerequisites

1. **Python 3.8+** - Download from python.org
2. **AWS Account** - Workshop account credentials
3. **AWS Credentials** - Already provided in AWS-Access-Info.txt

## Setup Instructions

### Step 1: Install Python

If Python is not installed:
1. Download from: https://www.python.org/downloads/
2. Run installer and check "Add Python to PATH"
3. Verify: `python --version`

### Step 2: Install Dependencies

```powershell
cd "c:\Users\tomasm\Desktop\UIC Enterprise AI Hackathon"
python -m pip install -r backend/requirements.txt
```

### Step 3: Configure AWS Credentials

Run the commands from `.kiro/specs/bedrock-setup/AWS-Access-Info.txt`:

```powershell
$Env:AWS_DEFAULT_REGION="us-east-1"
$Env:AWS_ACCESS_KEY_ID="<your-temporary-access-key-id>"
$Env:AWS_SECRET_ACCESS_KEY="<your-temporary-secret-access-key>"
$Env:AWS_SESSION_TOKEN="<your-temporary-session-token>"
```

**Note**: These are temporary credentials and will expire.

### Step 4: Run Connection Test

```powershell
python backend/test_bedrock_setup.py
```

## What the Test Does

The test script (`backend/test_bedrock_setup.py`) performs all Task 3.1 requirements:

1. **Validates AWS Credentials** - Checks if credentials are configured
2. **Initializes Bedrock Client** - Creates boto3 bedrock-runtime client with proper timeouts
3. **Tests Claude Haiku** - Sends test prompt to verify model access
4. **Tests Claude Sonnet** - Sends test prompt to verify model access  
5. **Stores Configuration** - Saves model IDs to AWS Parameter Store (optional)

## Expected Output

### Success Case:
```
============================================================
STEP 1: Testing AWS Credentials
============================================================
✓ AWS Credentials Valid
  Account: 605134453119
  User ARN: arn:aws:sts::605134453119:assumed-role/...

============================================================
STEP 2: Initializing Bedrock Client
============================================================
✓ Bedrock client initialized
  Region: us-east-1
  Service: bedrock-runtime

============================================================
STEP 3: Testing Model Connections
============================================================

Testing Claude Haiku
============================================================
✓ Connection successful
  Latency: 1234ms
  Response: Hello! This is a test response...

Testing Claude Sonnet
============================================================
✓ Connection successful
  Latency: 1456ms
  Response: Hello! This is a test response...

✅ SUCCESS: Task 3.1 Complete
```

### If Model Access Not Granted:
```
✗ Connection failed
  Error Code: AccessDeniedException
  Error Message: User: ... is not authorized to perform: bedrock:InvokeModel

  → Action Required: Request model access
     1. Go to AWS Console > Bedrock > Model access
     2. Request access for: anthropic.claude-3-haiku-20240307-v1:0
     3. Wait for approval (usually instant)
```

## Requesting Model Access

If you get `AccessDeniedException`:

1. Go to AWS Console: https://console.aws.amazon.com/bedrock/
2. Navigate to: **Bedrock > Model access** (left sidebar)
3. Click **"Request model access"** (orange button)
4. Find **"Claude 3 Haiku"** and **"Claude 3.5 Sonnet"** in the list
5. Check the boxes next to both models
6. Click **"Request model access"**
7. Wait ~30 seconds for approval
8. Re-run the test script

## Task 3.1 Checklist

- [x] Configure boto3 for bedrock-runtime ✓
- [ ] Request model access (Haiku & Sonnet) - Run test to verify
- [ ] Store model IDs in Parameter Store - Test script handles this
- [ ] Test connection with simple prompts - Test script validates

## Troubleshooting

### "Python was not found"
- Install Python from python.org
- Make sure "Add to PATH" is checked during installation

### "boto3 not installed"
```powershell
python -m pip install boto3
```

### "No AWS credentials found"
- Make sure you've run the credential commands in the same PowerShell window
- Credentials are session-only and will be lost if you close the terminal

### "AccessDeniedException"
- Follow the "Requesting Model Access" steps above

### "Temporary credentials expired"
- Get new credentials from your AWS workshop administrator
- Update AWS-Access-Info.txt with new values

## Next Steps

After Task 3.1 is complete:
- **Task 3.2**: Prompt Engineering - Create prompt templates
- **Task 3.3**: LLM Service - Build LLMService class
- **Task 3.4**: Change Tagging - Implement tag parsing

## Files Created

```
backend/
├── config/
│   ├── __init__.py
│   └── exceptions.py         # Custom exception classes
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   └── __init__.py
│   └── integration/
│       └── __init__.py
├── requirements.txt           # Python dependencies
├── test_bedrock_setup.py     # Task 3.1 validation script
└── README.md                  # This file
```

## Design Documents

Full technical design available in:
- `.kiro/specs/bedrock-setup/requirements.md`
- `.kiro/specs/bedrock-setup/design.md`
