USE zerowaste;

-- ===== Adding shops from the screen =====
-- status: PENDING while the start-up history and forecasts are being created, READY when done, FAILED on error
-- size_factor scales a shop's demand (small 0.7, medium 1.0, large 1.3). Run this file only once.
ALTER TABLE stores
  ADD COLUMN status VARCHAR(12) NOT NULL DEFAULT 'READY',
  ADD COLUMN status_message VARCHAR(255) NULL,
  ADD COLUMN size_factor DECIMAL(4,2) NOT NULL DEFAULT 1.00;

-- the four original shops keep the sizes they were simulated with
UPDATE stores SET size_factor = 1.20 WHERE store_id = 'S01';
UPDATE stores SET size_factor = 1.10 WHERE store_id = 'S02';
UPDATE stores SET size_factor = 0.90 WHERE store_id = 'S03';
UPDATE stores SET size_factor = 0.80 WHERE store_id = 'S04';
