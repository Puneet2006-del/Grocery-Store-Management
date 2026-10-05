USE zerowaste;

CREATE TABLE stores (
  store_id VARCHAR(10) PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  city VARCHAR(50) NOT NULL,
  type VARCHAR(20),
  lat DECIMAL(9,6),
  lon DECIMAL(9,6)
);

CREATE TABLE products (
  sku_id VARCHAR(10) PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  category VARCHAR(30) NOT NULL,
  shelf_life_days INT NOT NULL,
  unit VARCHAR(10),
  cost DECIMAL(8,2),
  base_price DECIMAL(8,2),
  storage_temp VARCHAR(20)
);

CREATE TABLE batches (
  batch_id VARCHAR(20) PRIMARY KEY,
  sku_id VARCHAR(10) NOT NULL,
  store_id VARCHAR(10) NOT NULL,
  received_date DATE NOT NULL,
  expiry_date DATE NOT NULL,
  qty_received INT NOT NULL,
  qty_remaining INT NOT NULL,
  FOREIGN KEY (sku_id) REFERENCES products(sku_id),
  FOREIGN KEY (store_id) REFERENCES stores(store_id)
);

CREATE TABLE sales (
  sale_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  sale_date DATE NOT NULL,
  store_id VARCHAR(10) NOT NULL,
  sku_id VARCHAR(10) NOT NULL,
  qty_sold INT NOT NULL,
  unit_price DECIMAL(8,2),
  revenue DECIMAL(10,2),
  promo_id VARCHAR(20),
  INDEX idx_sales (store_id, sku_id, sale_date)
);

CREATE TABLE promotions (
  promo_id VARCHAR(20) PRIMARY KEY,
  sku_id VARCHAR(10) NOT NULL,
  store_id VARCHAR(10) NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  discount_pct DECIMAL(5,2) NOT NULL,
  FOREIGN KEY (sku_id) REFERENCES products(sku_id),
  FOREIGN KEY (store_id) REFERENCES stores(store_id),
  INDEX idx_promo (store_id, sku_id, start_date, end_date)
);

CREATE TABLE receipts (
  receipt_id VARCHAR(20) PRIMARY KEY,
  sku_id VARCHAR(10) NOT NULL,
  store_id VARCHAR(10) NOT NULL,
  batch_id VARCHAR(20) NOT NULL,
  received_date DATE NOT NULL,
  qty INT NOT NULL,
  unit_cost DECIMAL(8,2),
  FOREIGN KEY (sku_id) REFERENCES products(sku_id),
  FOREIGN KEY (store_id) REFERENCES stores(store_id),
  FOREIGN KEY (batch_id) REFERENCES batches(batch_id),
  INDEX idx_receipts (store_id, sku_id, received_date)
);

CREATE TABLE inventory_snapshots (
  snapshot_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  snapshot_date DATE NOT NULL,
  store_id VARCHAR(10) NOT NULL,
  sku_id VARCHAR(10) NOT NULL,
  on_hand_qty INT NOT NULL,
  FOREIGN KEY (sku_id) REFERENCES products(sku_id),
  FOREIGN KEY (store_id) REFERENCES stores(store_id),
  UNIQUE KEY uq_snapshot (snapshot_date, store_id, sku_id),
  INDEX idx_inventory (store_id, sku_id, snapshot_date)
);

CREATE TABLE prices (
  price_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  sku_id VARCHAR(10) NOT NULL,
  store_id VARCHAR(10) NOT NULL,
  effective_date DATE NOT NULL,
  price DECIMAL(8,2) NOT NULL,
  FOREIGN KEY (sku_id) REFERENCES products(sku_id),
  FOREIGN KEY (store_id) REFERENCES stores(store_id),
  UNIQUE KEY uq_price (sku_id, store_id, effective_date)
);

CREATE TABLE waste (
  waste_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  waste_date DATE NOT NULL,
  store_id VARCHAR(10) NOT NULL,
  sku_id VARCHAR(10) NOT NULL,
  batch_id VARCHAR(20),
  qty INT NOT NULL,
  reason VARCHAR(20) NOT NULL,        -- expired / damaged
  cost DECIMAL(10,2),
  FOREIGN KEY (sku_id) REFERENCES products(sku_id),
  FOREIGN KEY (store_id) REFERENCES stores(store_id),
  FOREIGN KEY (batch_id) REFERENCES batches(batch_id),
  INDEX idx_waste (store_id, sku_id, waste_date)
);

CREATE TABLE weather (
  weather_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  weather_date DATE NOT NULL,
  city VARCHAR(50) NOT NULL,
  temp_c DECIMAL(4,1),
  rain_mm DECIMAL(5,1),
  UNIQUE KEY uq_weather (weather_date, city)
);

CREATE TABLE events (
  event_id VARCHAR(20) PRIMARY KEY,
  event_date DATE NOT NULL,
  city VARCHAR(50) NOT NULL,
  event_type VARCHAR(30) NOT NULL,    -- festival / holiday / match / concert
  expected_impact DECIMAL(4,2),       -- demand multiplier, e.g. 1.30 = +30%
  INDEX idx_events (city, event_date)
);