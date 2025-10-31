#!/bin/bash
set -e

echo "🚀 LiminalQA MVP-1 Demo Script"
echo "================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="../deploy/docker-compose.mvp1.yml"
INGEST_URL="http://localhost:8088"
API_TOKEN="devtoken"
SAMPLES_DIR="../samples"

# Step 1: Start services
echo "📦 Step 1: Starting services..."
cd "$(dirname "$0")"
docker compose -f $COMPOSE_FILE up -d

echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check health
until curl -sf "$INGEST_URL/health" > /dev/null; do
  echo "   Waiting for ingest service..."
  sleep 2
done

echo -e "${GREEN}✓${NC} All services are healthy!"
echo ""

# Step 2: Ingest sample data
echo "📝 Step 2: Ingesting sample data..."

echo "   → Ingesting run..."
curl -sf -X POST "$INGEST_URL/ingest/run" \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @"$SAMPLES_DIR/run.json" | jq .

echo "   → Ingesting tests..."
curl -sf -X POST "$INGEST_URL/ingest/tests" \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @"$SAMPLES_DIR/tests.json" | jq .

echo "   → Ingesting signals..."
curl -sf -X POST "$INGEST_URL/ingest/signals" \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @"$SAMPLES_DIR/signals.json" | jq .

echo "   → Ingesting artifacts..."
curl -sf -X POST "$INGEST_URL/ingest/artifacts" \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @"$SAMPLES_DIR/artifacts.json" | jq .

echo -e "${GREEN}✓${NC} Sample data ingested successfully!"
echo ""

# Step 3: Query database
echo "🔍 Step 3: Querying bi-temporal database..."

RUN_ID="01HJQKX8K9N7P6R5S3T2V1W0XY"

echo "   → Current test facts:"
docker exec liminal-postgres psql -U liminal -d liminal -c \
  "SELECT test_name, status, duration_ms FROM test_fact WHERE run_id = '$RUN_ID' AND valid_to = 'infinity' ORDER BY test_name;"

echo ""
echo "   → Causality walk (signals near failures):"
docker exec liminal-postgres psql -U liminal -d liminal -c \
  "SELECT test_name, signal_kind, signal_at, signal_value, time_diff_seconds FROM causality_walk('$RUN_ID') LIMIT 10;"

echo ""
echo "   → Resonance map (test results over time):"
docker exec liminal-postgres psql -U liminal -d liminal -c \
  "SELECT bucket, status, count FROM resonance_map('$RUN_ID');"

echo ""
echo -e "${GREEN}✓${NC} Database queries completed!"
echo ""

# Step 4: Generate report
echo "📊 Step 4: Generating reflection report..."
echo -e "${YELLOW}   (Report generation will be implemented in Task 5)${NC}"
echo ""

# Success
echo -e "${GREEN}✅ Demo completed successfully!${NC}"
echo ""
echo "📋 Summary:"
echo "   - Run ID: $RUN_ID"
echo "   - Tests: 4 (3 passed, 1 failed)"
echo "   - Signals: 5"
echo "   - Artifacts: 2"
echo ""
echo "🔗 Next steps:"
echo "   - View data: docker exec -it liminal-postgres psql -U liminal -d liminal"
echo "   - Stop services: docker compose -f $COMPOSE_FILE down"
echo "   - View logs: docker compose -f $COMPOSE_FILE logs -f ingest"
echo ""
