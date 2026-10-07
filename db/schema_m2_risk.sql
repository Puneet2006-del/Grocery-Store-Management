USE zerowaste;

-- Milestone 2: written by intelligence/risk_engine.py

CREATE TABLE IF NOT EXISTS batch_risk (
  run_date DATE NOT NULL,              -- the day the stock position is as of
  batch_id VARCHAR(20) NOT NULL,
  store_id VARCHAR(10) NOT NULL,
  sku_id VARCHAR(10) NOT NULL,
  expiry_date DATE NOT NULL,
  days_to_expiry INT NOT NULL,
  qty_remaining INT NOT NULL,
  expected_sold DECIMAL(10,2) NOT NULL,
  expected_unsold DECIMAL(10,2) NOT NULL,   -- units expected to expire unsold
  unsold_pct DECIMAL(5,1) NOT NULL,
  spoilage_prob DECIMAL(5,3) NOT NULL,      -- chance that more than 10% of the batch expires unsold
  expected_waste_cost DECIMAL(10,2) NOT NULL,
  risk_level VARCHAR(10) NOT NULL,          -- HIGH / MEDIUM / LOW
  PRIMARY KEY (run_date, batch_id),
  FOREIGN KEY (batch_id) REFERENCES batches(batch_id),
  FOREIGN KEY (store_id) REFERENCES stores(store_id),
  FOREIGN KEY (sku_id) REFERENCES products(sku_id),
  INDEX idx_batch_risk (store_id, sku_id)
);

CREATE TABLE IF NOT EXISTS sku_risk (
  run_date DATE NOT NULL,
  store_id VARCHAR(10) NOT NULL,
  sku_id VARCHAR(10) NOT NULL,
  on_hand_qty INT NOT NULL,
  forecast_7d_qty DECIMAL(10,2) NOT NULL,
  days_of_cover DECIMAL(6,2),
  next_delivery_date DATE NOT NULL,
  stockout_prob DECIMAL(5,3) NOT NULL,      -- chance stock runs out before the next delivery
  expected_shortfall DECIMAL(10,2) NOT NULL,
  expected_unsold DECIMAL(10,2) NOT NULL,   -- units expected to expire unsold
  excess_pct DECIMAL(5,1) NOT NULL,
  expected_waste_cost DECIMAL(10,2) NOT NULL,
  alert_type VARCHAR(20) NOT NULL,          -- STOCKOUT_RISK / EXCESS_STOCK / OK
  severity VARCHAR(10) NOT NULL,            -- HIGH / MEDIUM / LOW
  PRIMARY KEY (run_date, store_id, sku_id),
  FOREIGN KEY (store_id) REFERENCES stores(store_id),
  FOREIGN KEY (sku_id) REFERENCES products(sku_id)
);
