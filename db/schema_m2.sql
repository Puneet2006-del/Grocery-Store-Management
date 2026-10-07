USE zerowaste;

-- Milestone 2: forecasts written by intelligence/forecast_next_week.py
CREATE TABLE IF NOT EXISTS demand_forecasts (
  forecast_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  run_date DATE NOT NULL,            -- last day of data the forecast was made from
  forecast_date DATE NOT NULL,       -- the day being forecast
  horizon INT NOT NULL,              -- days ahead (1-7)
  store_id VARCHAR(10) NOT NULL,
  sku_id VARCHAR(10) NOT NULL,
  predicted_qty DECIMAL(10,2) NOT NULL,
  lower_qty DECIMAL(10,2) NOT NULL,  -- P10: demand is expected to exceed this 9 days in 10
  upper_qty DECIMAL(10,2) NOT NULL,  -- P90: demand is expected to stay below this 9 days in 10
  model_version VARCHAR(40) NOT NULL,
  FOREIGN KEY (store_id) REFERENCES stores(store_id),
  FOREIGN KEY (sku_id) REFERENCES products(sku_id),
  UNIQUE KEY uq_forecast (run_date, forecast_date, store_id, sku_id),
  INDEX idx_forecast (store_id, sku_id, forecast_date)
);
