package com.zerowaste.grocery.service;

import com.zerowaste.grocery.dto.IntelligenceDtos.BatchRiskDto;
import com.zerowaste.grocery.dto.IntelligenceDtos.ForecastDto;
import com.zerowaste.grocery.dto.IntelligenceDtos.SkuRiskDto;
import java.sql.Date;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import javax.sql.DataSource;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

/**
 * Reads the tables written by the Python intelligence layer (demand_forecasts, batch_risk, sku_risk).
 * Plain SQL is used because these tables are read-only for the backend.
 */
@Service
public class IntelligenceService {

    private final JdbcClient jdbc;

    public IntelligenceService(DataSource dataSource) {
        this.jdbc = JdbcClient.create(dataSource);
    }

    private static LocalDate date(java.sql.ResultSet rs, String col) throws java.sql.SQLException {
        Date d = rs.getDate(col);
        return d == null ? null : d.toLocalDate();
    }

    /** Most recent run date in a table, or null when the table is empty. */
    public LocalDate latestRunDate(String table) {
        List<LocalDate> rows = jdbc.sql("SELECT MAX(run_date) AS d FROM " + table)
                .query((rs, i) -> date(rs, "d")).list();
        return rows.isEmpty() ? null : rows.get(0);
    }

    private LocalDate resolve(String table, LocalDate runDate) {
        return runDate != null ? runDate : latestRunDate(table);
    }

    public List<ForecastDto> forecasts(String storeId, String skuId, LocalDate runDate) {
        LocalDate run = resolve("demand_forecasts", runDate);
        if (run == null) {
            return List.of();
        }
        StringBuilder sql = new StringBuilder("""
                SELECT f.run_date, f.forecast_date, f.horizon, f.store_id, s.name AS store_name,
                       f.sku_id, p.name AS product_name, f.predicted_qty, f.lower_qty, f.upper_qty,
                       f.model_version
                FROM demand_forecasts f
                JOIN stores s ON s.store_id = f.store_id
                JOIN products p ON p.sku_id = f.sku_id
                WHERE f.run_date = :runDate
                """);
        Map<String, Object> params = new HashMap<>();
        params.put("runDate", run);
        if (storeId != null) {
            sql.append(" AND f.store_id = :storeId");
            params.put("storeId", storeId);
        }
        if (skuId != null) {
            sql.append(" AND f.sku_id = :skuId");
            params.put("skuId", skuId);
        }
        sql.append(" ORDER BY f.store_id, f.sku_id, f.horizon");
        return jdbc.sql(sql.toString()).params(params).query((rs, i) -> new ForecastDto(
                date(rs, "run_date"), date(rs, "forecast_date"), rs.getInt("horizon"),
                rs.getString("store_id"), rs.getString("store_name"), rs.getString("sku_id"),
                rs.getString("product_name"), rs.getBigDecimal("predicted_qty"),
                rs.getBigDecimal("lower_qty"), rs.getBigDecimal("upper_qty"),
                rs.getString("model_version"))).list();
    }

    public List<BatchRiskDto> batchRisk(String storeId, String skuId, String riskLevel, LocalDate runDate) {
        LocalDate run = resolve("batch_risk", runDate);
        if (run == null) {
            return List.of();
        }
        StringBuilder sql = new StringBuilder("""
                SELECT r.run_date, r.batch_id, r.store_id, s.name AS store_name, r.sku_id,
                       p.name AS product_name, p.category, r.expiry_date, r.days_to_expiry,
                       r.qty_remaining, r.expected_sold, r.expected_unsold, r.unsold_pct,
                       r.spoilage_prob, r.expected_waste_cost, r.risk_level
                FROM batch_risk r
                JOIN stores s ON s.store_id = r.store_id
                JOIN products p ON p.sku_id = r.sku_id
                WHERE r.run_date = :runDate
                """);
        Map<String, Object> params = new HashMap<>();
        params.put("runDate", run);
        if (storeId != null) {
            sql.append(" AND r.store_id = :storeId");
            params.put("storeId", storeId);
        }
        if (skuId != null) {
            sql.append(" AND r.sku_id = :skuId");
            params.put("skuId", skuId);
        }
        if (riskLevel != null) {
            sql.append(" AND r.risk_level = :riskLevel");
            params.put("riskLevel", riskLevel);
        }
        sql.append(" ORDER BY r.expected_waste_cost DESC, r.batch_id");
        return jdbc.sql(sql.toString()).params(params).query((rs, i) -> new BatchRiskDto(
                date(rs, "run_date"), rs.getString("batch_id"), rs.getString("store_id"),
                rs.getString("store_name"), rs.getString("sku_id"), rs.getString("product_name"),
                rs.getString("category"), date(rs, "expiry_date"), rs.getInt("days_to_expiry"),
                rs.getInt("qty_remaining"), rs.getBigDecimal("expected_sold"),
                rs.getBigDecimal("expected_unsold"), rs.getBigDecimal("unsold_pct"),
                rs.getBigDecimal("spoilage_prob"), rs.getBigDecimal("expected_waste_cost"),
                rs.getString("risk_level"))).list();
    }

    public List<SkuRiskDto> skuRisk(String storeId, String category, String alertType,
                                    String severity, LocalDate runDate) {
        LocalDate run = resolve("sku_risk", runDate);
        if (run == null) {
            return List.of();
        }
        StringBuilder sql = new StringBuilder("""
                SELECT r.run_date, r.store_id, s.name AS store_name, r.sku_id, p.name AS product_name,
                       p.category, r.on_hand_qty, r.forecast_7d_qty, r.days_of_cover,
                       r.next_delivery_date, r.stockout_prob, r.expected_shortfall, r.expected_unsold,
                       r.excess_pct, r.expected_waste_cost, r.alert_type, r.severity
                FROM sku_risk r
                JOIN stores s ON s.store_id = r.store_id
                JOIN products p ON p.sku_id = r.sku_id
                WHERE r.run_date = :runDate
                """);
        Map<String, Object> params = new HashMap<>();
        params.put("runDate", run);
        if (storeId != null) {
            sql.append(" AND r.store_id = :storeId");
            params.put("storeId", storeId);
        }
        if (category != null) {
            sql.append(" AND LOWER(p.category) = :category");
            params.put("category", category.toLowerCase());
        }
        if (alertType != null) {
            sql.append(" AND r.alert_type = :alertType");
            params.put("alertType", alertType);
        }
        if (severity != null) {
            sql.append(" AND r.severity = :severity");
            params.put("severity", severity);
        }
        sql.append(" ORDER BY CASE r.severity WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END,"
                + " r.expected_waste_cost DESC, r.store_id, r.sku_id");
        return jdbc.sql(sql.toString()).params(params).query((rs, i) -> new SkuRiskDto(
                date(rs, "run_date"), rs.getString("store_id"), rs.getString("store_name"),
                rs.getString("sku_id"), rs.getString("product_name"), rs.getString("category"),
                rs.getInt("on_hand_qty"), rs.getBigDecimal("forecast_7d_qty"),
                rs.getBigDecimal("days_of_cover"), date(rs, "next_delivery_date"),
                rs.getBigDecimal("stockout_prob"), rs.getBigDecimal("expected_shortfall"),
                rs.getBigDecimal("expected_unsold"), rs.getBigDecimal("excess_pct"),
                rs.getBigDecimal("expected_waste_cost"), rs.getString("alert_type"),
                rs.getString("severity"))).list();
    }

    /** Headline numbers for a dashboard: alert counts and expected waste. */
    public Map<String, Object> summary(LocalDate runDate) {
        LocalDate run = resolve("batch_risk", runDate);
        Map<String, Object> out = new LinkedHashMap<>();
        if (run == null) {
            out.put("runDate", null);
            return out;
        }
        out.put("runDate", run.toString());

        Map<String, Object> batchLevels = new LinkedHashMap<>();
        jdbc.sql("SELECT risk_level, COUNT(*) AS c FROM batch_risk WHERE run_date = :d GROUP BY risk_level")
                .param("d", run).query((rs, i) -> {
                    batchLevels.put(rs.getString("risk_level"), rs.getInt("c"));
                    return rs.getString("risk_level");
                }).list();
        out.put("batchesByRiskLevel", batchLevels);

        Map<String, Object> alerts = new LinkedHashMap<>();
        jdbc.sql("SELECT alert_type, severity, COUNT(*) AS c FROM sku_risk WHERE run_date = :d "
                        + "GROUP BY alert_type, severity ORDER BY alert_type, severity")
                .param("d", run).query((rs, i) -> {
                    alerts.put(rs.getString("alert_type") + "_" + rs.getString("severity"), rs.getInt("c"));
                    return rs.getString("alert_type");
                }).list();
        out.put("skuAlerts", alerts);

        List<Map<String, Object>> waste = jdbc.sql("""
                SELECT COALESCE(SUM(expected_unsold), 0) AS units,
                       COALESCE(SUM(expected_waste_cost), 0) AS cost,
                       COALESCE(SUM(CASE WHEN days_to_expiry <= 1 THEN expected_unsold ELSE 0 END), 0) AS late_units,
                       COALESCE(SUM(CASE WHEN days_to_expiry <= 1 THEN expected_waste_cost ELSE 0 END), 0) AS late_cost
                FROM batch_risk WHERE run_date = :d
                """).param("d", run).query((rs, i) -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("expectedUnsoldUnits", rs.getBigDecimal("units"));
            m.put("expectedWasteCost", rs.getBigDecimal("cost"));
            m.put("unavoidableUnits", rs.getBigDecimal("late_units"));
            m.put("unavoidableCost", rs.getBigDecimal("late_cost"));
            return m;
        }).list();
        out.put("expectedWaste", waste.isEmpty() ? new ArrayList<>() : waste.get(0));
        return out;
    }
}
