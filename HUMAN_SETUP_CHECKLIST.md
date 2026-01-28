# Human Setup Checklist (Bronze MVP — Sprints 1-6)

## 1. Local Development Environment
- [ ] Python 3.11+ installed
- [ ] Clone repo and `pip install -e ".[dev]"`
- [ ] Copy `.env.example` to `.env` and fill in values

## 2. AWS Account & Credentials
- [ ] AWS account with CLI credentials configured (`aws configure` or env vars)
- [ ] IAM permissions: s3, ecs, ecr, events, cloudwatch, cloudformation, iam, sns, logs

## 3. Environment Variables (`.env`)
- [ ] `BRONZE_BUCKET` — your S3 bucket name (**required**)
- [ ] `AWS_REGION` — defaults to `us-east-1` if unset
- [ ] `LOG_LEVEL` — defaults to `INFO` if unset

## 4. Kalshi API Access (required for Kalshi ingestion)
- [ ] Kalshi account created (https://kalshi.com)
- [ ] API key generated in Kalshi dashboard
- [ ] RSA private key PEM file saved locally
- [ ] `KALSHI_API_KEY_ID` set in `.env`
- [ ] `KALSHI_PRIVATE_KEY_PATH` set in `.env` (path to PEM file)

## 5. Polymarket
- [ ] Nothing needed — public API, no credentials required

## 6. VPC & Networking (required for ECS/Fargate)
- [ ] VPC exists with at least one subnet that has outbound internet access
- [ ] Security group allows outbound HTTPS (port 443) to external APIs and S3
- [ ] Note your `SubnetIds` and `SecurityGroupIds` for CloudFormation parameters

## 7. ECR Repository & Docker Image
- [ ] Create ECR repository:
  ```bash
  aws ecr create-repository --repository-name prediction-data --region $AWS_REGION
  ```
- [ ] Build and push the Docker image:
  ```bash
  # Authenticate Docker to ECR
  aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.$AWS_REGION.amazonaws.com

  # Build and push
  docker build -t prediction-data .
  docker tag prediction-data:latest <ACCOUNT_ID>.dkr.ecr.$AWS_REGION.amazonaws.com/prediction-data:latest
  docker push <ACCOUNT_ID>.dkr.ecr.$AWS_REGION.amazonaws.com/prediction-data:latest
  ```

## 8. Deploy CloudFormation Stacks (in order)

Deploy each stack in sequence. See `infrastructure/README.md` for full details.

1. **S3 Bronze Bucket**
   ```bash
   aws cloudformation deploy --template-file infrastructure/s3-bronze-bucket.yaml \
     --stack-name prediction-bronze-bucket --parameter-overrides Environment=prod
   ```

2. **IAM Roles**
   ```bash
   aws cloudformation deploy --template-file infrastructure/iam-ecs-roles.yaml \
     --stack-name prediction-data-iam-roles --capabilities CAPABILITY_NAMED_IAM \
     --parameter-overrides Environment=prod
   ```

3. **ECS Cluster & Task Definition**
   ```bash
   aws cloudformation deploy --template-file infrastructure/ecs-cluster.yaml \
     --stack-name prediction-data-ecs \
     --parameter-overrides Environment=prod ContainerImage=<ACCOUNT_ID>.dkr.ecr.$AWS_REGION.amazonaws.com/prediction-data:latest
   ```

4. **EventBridge Schedules**
   ```bash
   aws cloudformation deploy --template-file infrastructure/eventbridge-schedules.yaml \
     --stack-name prediction-data-schedules \
     --parameter-overrides Environment=prod SubnetIds=subnet-xxx SecurityGroupIds=sg-xxx
   ```

5. **CloudWatch Monitoring**
   ```bash
   aws cloudformation deploy --template-file infrastructure/cloudwatch-monitoring.yaml \
     --stack-name prediction-data-monitoring \
     --parameter-overrides Environment=prod AlertEmail=you@example.com
   ```

## 9. Kalshi Secrets in AWS Secrets Manager (optional)
- [ ] Store Kalshi credentials if using Secrets Manager instead of env vars:
  ```bash
  aws secretsmanager create-secret --name prediction-data/kalshi-api-key-id --secret-string "YOUR_KEY_ID"
  aws secretsmanager create-secret --name prediction-data/kalshi-private-key --secret-string file://path/to/private.pem
  ```

## 10. Post-Deployment
- [ ] **Confirm SNS email subscription** — check inbox and click the confirmation link
- [ ] **Smoke test** — manually trigger one ECS task:
  ```bash
  aws ecs run-task \
    --cluster prediction-data \
    --task-definition prediction-data-ingest \
    --launch-type FARGATE \
    --network-configuration '{"awsvpcConfiguration":{"subnets":["subnet-xxx"],"securityGroups":["sg-xxx"],"assignPublicIp":"ENABLED"}}' \
    --overrides '{"containerOverrides":[{"name":"app","command":["prediction-data","ingest","polymarket-markets","--dt","2026-01-28"]}]}'
  ```
- [ ] **Verify S3 output** — confirm `part-000.jsonl.gz` and `manifest.json` landed
- [ ] **Verify CloudWatch logs** — confirm structured log output appears
- [ ] **Verify EventBridge schedules are active** — check that scheduled runs fire on cadence

## 11. Verify Everything Works
```bash
# Run the local verification script
python scripts/check_setup.py

# Quick local smoke tests
prediction-data --version
prediction-data ingest polymarket-markets --dt 2026-01-01
```
