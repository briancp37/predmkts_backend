#!/usr/bin/env bash
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/prediction-data"

echo "=== Pushing prediction-data image to ECR ==="
echo "Account: ${ACCOUNT_ID}"
echo "ECR URI: ${ECR_URI}"
echo

echo "[1/3] Logging in to ECR..."
aws ecr get-login-password --region "${REGION}" | \
  docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo
echo "[2/3] Building Docker image..."
docker build -t prediction-data "$(dirname "$0")/.."

echo
echo "[3/3] Tagging and pushing..."
docker tag prediction-data:latest "${ECR_URI}:latest"
docker push "${ECR_URI}:latest"

echo
echo "Done. Image pushed to ${ECR_URI}:latest"
