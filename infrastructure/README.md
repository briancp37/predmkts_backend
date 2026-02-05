# Prediction Data - AWS Infrastructure

CloudFormation templates for the Bronze-level prediction data ingestion pipeline.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    EventBridge Scheduler                     │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │polymarket-order- │  │  kalshi-trades   │  (every 5 min) │
│  │filled, markets   │  │  kalshi-markets  │  (every 1 hr)  │
│  └────────┬─────────┘  └────────┬─────────┘                │
│           └──────────┬──────────┘                           │
└──────────────────────┼──────────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                      ECS Fargate Cluster                     │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Task Definition: prediction-data-ingest-{env}         │  │
│  │  Image: ECR prediction-data:latest                     │  │
│  │  CPU: 0.25 vCPU | Memory: 512 MB                      │  │
│  │  Command: ingest {platform}-{entity} --dt {date}       │  │
│  └────────────────────┬───────────────────────────────────┘  │
└───────────────────────┼──────────────────────────────────────┘
                        │
              ┌─────────┼─────────┐
              ▼                   ▼
┌──────────────────┐   ┌──────────────────────────────────────┐
│   S3 Bronze      │   │         CloudWatch                    │
│   Bucket         │   │  ┌─────────────┐ ┌────────────────┐  │
│  prediction-     │   │  │ Log Group   │ │ Alarms (6)     │  │
│  bronze-{env}    │   │  │ /ecs/pred.. │ │ errors, fails, │  │
│                  │   │  └─────────────┘ │ missing runs   │  │
│  SSE-S3 encrypted│   │  ┌─────────────┐ └───────┬────────┘  │
│  Versioning on   │   │  │ Dashboard   │         │            │
└──────────────────┘   │  └─────────────┘         ▼            │
                       │                  ┌──────────────┐     │
                       │                  │  SNS Topic   │     │
                       │                  │  → Email     │     │
                       │                  └──────────────┘     │
                       └───────────────────────────────────────┘
```

## Templates

| Template | Stack Name | Description |
|---|---|---|
| `s3-bronze-bucket.yaml` | `prediction-bronze-bucket` | S3 bucket with versioning, encryption, lifecycle rules |
| `iam-ecs-roles.yaml` | `prediction-data-iam-roles` | Task execution role and task role (least-privilege) |
| `ecs-cluster.yaml` | `prediction-data-ecs` | ECS cluster, task definition, log group |
| `eventbridge-schedules.yaml` | `prediction-data-schedules` | 4 scheduled ingestion jobs |
| `eventbridge-gold-schedules.yaml` | `prediction-data-gold-schedules` | 3 Gold layer daily processing schedules |
| `eventbridge-silver-schedules.yaml` | `prediction-data-silver-schedules` | 11 Silver layer near-continuous processing schedules |
| `cloudwatch-monitoring.yaml` | `prediction-data-monitoring` | Alarms, metric filters, dashboard, SNS alerts |

## Deployment Order

Templates must be deployed in order due to cross-stack dependencies:

```bash
ENV=dev
REGION=us-east-1
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# 1. S3 Bucket
aws cloudformation deploy \
  --template-file infrastructure/s3-bronze-bucket.yaml \
  --stack-name prediction-bronze-bucket \
  --parameter-overrides Environment=$ENV

# 2. IAM Roles (needs bucket ARN)
aws cloudformation deploy \
  --template-file infrastructure/iam-ecs-roles.yaml \
  --stack-name prediction-data-iam-roles \
  --parameter-overrides \
    Environment=$ENV \
    BronzeBucketArn=arn:aws:s3:::prediction-bronze-$ENV \
  --capabilities CAPABILITY_NAMED_IAM

# 3. Create ECR repository and push image
aws ecr create-repository --repository-name prediction-data
docker build -t prediction-data .
docker tag prediction-data:latest $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/prediction-data:latest
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/prediction-data:latest

# 4. ECS Cluster (needs IAM role ARNs and ECR image URI)
EXEC_ROLE=$(aws cloudformation describe-stacks --stack-name prediction-data-iam-roles \
  --query "Stacks[0].Outputs[?OutputKey=='TaskExecutionRoleArn'].OutputValue" --output text)
TASK_ROLE=$(aws cloudformation describe-stacks --stack-name prediction-data-iam-roles \
  --query "Stacks[0].Outputs[?OutputKey=='TaskRoleArn'].OutputValue" --output text)

aws cloudformation deploy \
  --template-file infrastructure/ecs-cluster.yaml \
  --stack-name prediction-data-ecs \
  --parameter-overrides \
    Environment=$ENV \
    ECRImageUri=$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/prediction-data:latest \
    TaskExecutionRoleArn=$EXEC_ROLE \
    TaskRoleArn=$TASK_ROLE \
    BronzeBucketName=prediction-bronze-$ENV

# 5. EventBridge Schedules (needs ECS cluster and task definition ARNs, VPC config)
CLUSTER_ARN=$(aws cloudformation describe-stacks --stack-name prediction-data-ecs \
  --query "Stacks[0].Outputs[?OutputKey=='ClusterArn'].OutputValue" --output text)
TASK_DEF_ARN=$(aws cloudformation describe-stacks --stack-name prediction-data-ecs \
  --query "Stacks[0].Outputs[?OutputKey=='TaskDefinitionArn'].OutputValue" --output text)

aws cloudformation deploy \
  --template-file infrastructure/eventbridge-schedules.yaml \
  --stack-name prediction-data-schedules \
  --parameter-overrides \
    Environment=$ENV \
    ECSClusterArn=$CLUSTER_ARN \
    TaskDefinitionArn=$TASK_DEF_ARN \
    SubnetIds=<your-subnet-ids> \
    SecurityGroupIds=<your-security-group-id> \
  --capabilities CAPABILITY_NAMED_IAM

# 5b. EventBridge Gold Schedules (needs ECS cluster and task definition ARNs, VPC config)
aws cloudformation deploy \
  --template-file infrastructure/eventbridge-gold-schedules.yaml \
  --stack-name prediction-data-gold-schedules \
  --parameter-overrides \
    Environment=$ENV \
    ECSClusterArn=$CLUSTER_ARN \
    TaskDefinitionArn=$TASK_DEF_ARN \
    SubnetIds=<your-subnet-ids> \
    SecurityGroupIds=<your-security-group-id> \
  --capabilities CAPABILITY_NAMED_IAM

# 5c. EventBridge Silver Schedules (near-continuous Silver processing)
aws cloudformation deploy \
  --template-file infrastructure/eventbridge-silver-schedules.yaml \
  --stack-name prediction-data-silver-schedules \
  --parameter-overrides \
    Environment=$ENV \
    ECSClusterArn=$CLUSTER_ARN \
    TaskDefinitionArn=$TASK_DEF_ARN \
    SubnetIds=<your-subnet-ids> \
    SecurityGroupIds=<your-security-group-id> \
  --capabilities CAPABILITY_NAMED_IAM

# 6. CloudWatch Monitoring (needs log group and cluster name)
aws cloudformation deploy \
  --template-file infrastructure/cloudwatch-monitoring.yaml \
  --stack-name prediction-data-monitoring \
  --parameter-overrides \
    Environment=$ENV \
    LogGroupName=/ecs/prediction-data-$ENV \
    ECSClusterName=prediction-data-$ENV \
    AlertEmail=your-email@example.com
```

## Rollback Procedures

Stacks must be deleted in **reverse** deployment order to respect dependencies:

```bash
# Delete in reverse order
aws cloudformation delete-stack --stack-name prediction-data-monitoring
aws cloudformation wait stack-delete-complete --stack-name prediction-data-monitoring

aws cloudformation delete-stack --stack-name prediction-data-silver-schedules
aws cloudformation wait stack-delete-complete --stack-name prediction-data-silver-schedules

aws cloudformation delete-stack --stack-name prediction-data-gold-schedules
aws cloudformation wait stack-delete-complete --stack-name prediction-data-gold-schedules

aws cloudformation delete-stack --stack-name prediction-data-schedules
aws cloudformation wait stack-delete-complete --stack-name prediction-data-schedules

aws cloudformation delete-stack --stack-name prediction-data-ecs
aws cloudformation wait stack-delete-complete --stack-name prediction-data-ecs

aws cloudformation delete-stack --stack-name prediction-data-iam-roles
aws cloudformation wait stack-delete-complete --stack-name prediction-data-iam-roles

# S3 bucket must be emptied before deletion
aws s3 rm s3://prediction-bronze-$ENV --recursive
aws cloudformation delete-stack --stack-name prediction-bronze-bucket
aws cloudformation wait stack-delete-complete --stack-name prediction-bronze-bucket

# ECR repository (manual)
aws ecr delete-repository --repository-name prediction-data --force
```

To rollback a single stack update (revert to previous version):

```bash
aws cloudformation rollback-stack --stack-name <stack-name>
```

## Resource Summary

All resources are parameterized by environment (`dev`, `staging`, `prod`).

| Resource | Name Pattern |
|---|---|
| S3 Bucket | `prediction-bronze-{env}` |
| ECS Cluster | `prediction-data-{env}` |
| Task Definition | `prediction-data-ingest-{env}` |
| Log Group | `/ecs/prediction-data-{env}` |
| SNS Topic | `prediction-data-alerts-{env}` |
| Dashboard | `prediction-data-{env}` |
| Schedule Group (Bronze/Silver) | `prediction-data-{env}` |
| Schedule Group (Gold) | `prediction-data-gold-{env}` |
| Schedule Group (Silver) | `prediction-data-silver-{env}` |
| IAM Execution Role | `prediction-data-execution-{env}` |
| IAM Task Role | `prediction-data-task-{env}` |
