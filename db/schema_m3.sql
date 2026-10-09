USE zerowaste;

-- ===== Milestone 3: agentic decision engine =====

-- Configurable business rules (planners can edit values; re-running this file keeps their edits)
CREATE TABLE IF NOT EXISTS business_rules (
  rule_key VARCHAR(50) PRIMARY KEY,
  rule_value VARCHAR(100) NOT NULL,
  description VARCHAR(255),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

INSERT IGNORE INTO business_rules (rule_key, rule_value, description) VALUES
  ('service_level_target', '0.95', 'Replenishment covers demand up to this probability (forecast quantile)'),
  ('min_confidence', '0.50', 'Recommendations below this confidence are not proposed'),
  ('order_pack_size', '5', 'Order quantities are rounded up to a multiple of this'),
  ('spoilage_trigger_pct', '15', 'Consider markdown or transfer when this % of stock is expected to expire unsold'),
  ('max_markdown_pct', '50', 'Largest markdown allowed'),
  ('markdown_steps', '10,20,30,40,50', 'Markdown levels the markdown agent may choose from (%)'),
  ('min_price_over_cost_pct', '5', 'Marked-down price must stay at least this % above unit cost'),
  ('markdown_uplift_per_pct', '0.03', 'Assumed demand increase per 1% markdown (3% by default)'),
  ('min_transfer_qty', '10', 'Smallest quantity worth moving between stores'),
  ('max_transfer_km', '40', 'Longest allowed distance for an inter-store transfer'),
  ('transfer_fixed_cost', '150', 'Fixed cost of one transfer (INR)'),
  ('transfer_cost_per_unit_km', '0.15', 'Transport cost per unit per km (INR)'),
  ('min_days_left_at_receiver', '2', 'Transferred stock must have at least this many days left on arrival'),
  ('require_planner_approval', 'true', 'All actions need planner approval before execution');

-- One recommended action per store and SKU per run
CREATE TABLE IF NOT EXISTS recommendations (
  rec_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  run_date DATE NOT NULL,
  store_id VARCHAR(10) NOT NULL,
  sku_id VARCHAR(10) NOT NULL,
  action_type VARCHAR(20) NOT NULL,             -- REPLENISH / MARKDOWN / TRANSFER
  action_date DATE NOT NULL,                    -- when to carry it out
  timing_note VARCHAR(120),
  quantity INT,                                 -- order or transfer quantity
  markdown_pct DECIMAL(5,2),                    -- markdown level
  counterpart_store_id VARCHAR(10),             -- transfer destination
  confidence DECIMAL(4,3) NOT NULL,
  expected_waste_avoided_units DECIMAL(10,2) NOT NULL DEFAULT 0,
  expected_lost_sales_avoided_units DECIMAL(10,2) NOT NULL DEFAULT 0,
  expected_net_benefit DECIMAL(12,2) NOT NULL,  -- INR
  effect_summary VARCHAR(255),
  rationale TEXT,
  evidence JSON,                                -- forecasts, risks, batches and rules behind the decision
  status VARCHAR(12) NOT NULL DEFAULT 'PROPOSED',   -- PROPOSED / APPROVED / MODIFIED / REJECTED / EXECUTED
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (store_id) REFERENCES stores(store_id),
  FOREIGN KEY (sku_id) REFERENCES products(sku_id),
  FOREIGN KEY (counterpart_store_id) REFERENCES stores(store_id),
  UNIQUE KEY uq_rec (run_date, store_id, sku_id),
  INDEX idx_rec_status (run_date, status)
);

-- Every option the agents proposed for a store/SKU, so the comparison can be shown
CREATE TABLE IF NOT EXISTS recommendation_options (
  option_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  rec_id BIGINT NOT NULL,
  agent VARCHAR(20) NOT NULL,                   -- replenishment / markdown / transfer
  action_type VARCHAR(20) NOT NULL,
  quantity INT,
  markdown_pct DECIMAL(5,2),
  counterpart_store_id VARCHAR(10),
  expected_net_benefit DECIMAL(12,2) NOT NULL,
  confidence DECIMAL(4,3) NOT NULL,
  feasible BOOLEAN NOT NULL,                    -- false when a business rule blocks it
  rule_notes VARCHAR(255),
  chosen BOOLEAN NOT NULL DEFAULT FALSE,
  FOREIGN KEY (rec_id) REFERENCES recommendations(rec_id) ON DELETE CASCADE,
  INDEX idx_option_rec (rec_id)
);

-- What the planner did with each recommendation
CREATE TABLE IF NOT EXISTS decision_log (
  log_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  rec_id BIGINT NOT NULL,
  decided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  decided_by VARCHAR(50) NOT NULL,
  decision VARCHAR(12) NOT NULL,                -- APPROVED / MODIFIED / REJECTED
  before_json JSON,
  after_json JSON,
  comment VARCHAR(500),
  FOREIGN KEY (rec_id) REFERENCES recommendations(rec_id),
  INDEX idx_decision_rec (rec_id)
);

-- Outcomes and planner feedback, used to judge recommendations afterwards
CREATE TABLE IF NOT EXISTS feedback_log (
  feedback_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  rec_id BIGINT NOT NULL,
  recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  outcome VARCHAR(20) NOT NULL,                 -- EXECUTED / FAILED / OBSERVED
  actual_waste_units DECIMAL(10,2),
  actual_lost_sales_units DECIMAL(10,2),
  planner_rating INT,                           -- 1 to 5
  comment VARCHAR(500),
  FOREIGN KEY (rec_id) REFERENCES recommendations(rec_id),
  INDEX idx_feedback_rec (rec_id)
);

-- Simulated retail systems that receive approved actions
CREATE TABLE IF NOT EXISTS sim_erp_orders (
  po_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  rec_id BIGINT NOT NULL,
  store_id VARCHAR(10) NOT NULL,
  sku_id VARCHAR(10) NOT NULL,
  qty INT NOT NULL,
  order_date DATE NOT NULL,
  expected_delivery_date DATE,
  status VARCHAR(12) NOT NULL DEFAULT 'SENT',
  response_message VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (rec_id) REFERENCES recommendations(rec_id)
);

CREATE TABLE IF NOT EXISTS sim_wms_transfers (
  transfer_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  rec_id BIGINT NOT NULL,
  from_store_id VARCHAR(10) NOT NULL,
  to_store_id VARCHAR(10) NOT NULL,
  sku_id VARCHAR(10) NOT NULL,
  qty INT NOT NULL,
  status VARCHAR(12) NOT NULL DEFAULT 'SENT',
  response_message VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (rec_id) REFERENCES recommendations(rec_id)
);

CREATE TABLE IF NOT EXISTS sim_pos_price_changes (
  change_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  rec_id BIGINT NOT NULL,
  store_id VARCHAR(10) NOT NULL,
  sku_id VARCHAR(10) NOT NULL,
  markdown_pct DECIMAL(5,2) NOT NULL,
  new_price DECIMAL(8,2) NOT NULL,
  effective_date DATE NOT NULL,
  status VARCHAR(12) NOT NULL DEFAULT 'SENT',
  response_message VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (rec_id) REFERENCES recommendations(rec_id)
);
