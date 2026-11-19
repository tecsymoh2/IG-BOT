#!/usr/bin/env bash
# Copies every non-empty KEY=VALUE from .env into your Vercel project (production + preview).
# Usage: vercel link   (once)   then   bash scripts/push_env.sh
set -e
[ -f .env ] || { echo ".env not found"; exit 1; }
while IFS='=' read -r key value; do
  [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
  value="${value%\"}"; value="${value#\"}"
  [ -z "$value" ] && continue
  for target in production preview; do
    printf '%s' "$value" | vercel env add "$key" "$target" --force >/dev/null 2>&1 || true
  done
  echo "pushed $key"
done < .env
echo "Done. Redeploy with: vercel --prod"
