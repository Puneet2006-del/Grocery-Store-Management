package com.zerowaste.grocery.service;

import com.zerowaste.grocery.dto.PlannerDtos.DecisionDto;
import com.zerowaste.grocery.dto.PlannerDtos.DecisionRequest;
import com.zerowaste.grocery.dto.PlannerDtos.ModifyRequest;
import com.zerowaste.grocery.dto.PlannerDtos.OptionDto;
import com.zerowaste.grocery.dto.PlannerDtos.RecommendationDetailDto;
import com.zerowaste.grocery.dto.PlannerDtos.RecommendationDto;
import com.zerowaste.grocery.exception.ResourceNotFoundException;
import java.math.BigDecimal;
import java.sql.Date;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import javax.sql.DataSource;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Planner workflow: list recommendations, then approve, modify or reject them.
 * Every decision is written to decision_log with the values before and after.
 */
@Service
public class RecommendationService {

    private static final String SELECT_REC = """
            SELECT r.rec_id, r.run_date, r.store_id, s.name AS store_name, r.sku_id, p.name AS product_name,
                   p.category, r.action_type, r.action_date, r.timing_note, r.quantity, r.markdown_pct,
                   r.counterpart_store_id, cs.name AS counterpart_name, r.confidence,
                   r.expected_waste_avoided_units, r.expected_lost_sales_avoided_units, r.expected_net_benefit,
                   r.effect_summary, r.rationale, r.status, r.created_at
            FROM recommendations r
            JOIN stores s ON s.store_id = r.store_id
            JOIN products p ON p.sku_id = r.sku_id
            LEFT JOIN stores cs ON cs.store_id = r.counterpart_store_id
            """;

    private final JdbcClient jdbc;
    private final RuleService rules;

    public RecommendationService(DataSource dataSource, RuleService rules) {
        this.jdbc = JdbcClient.create(dataSource);
        this.rules = rules;
    }

    // ------------------------------------------------------------------ mapping
    private static LocalDate date(ResultSet rs, String col) throws SQLException {
        Date d = rs.getDate(col);
        return d == null ? null : d.toLocalDate();
    }

    private static RecommendationDto mapRec(ResultSet rs) throws SQLException {
        Timestamp created = rs.getTimestamp("created_at");
        return new RecommendationDto(rs.getLong("rec_id"), date(rs, "run_date"), rs.getString("store_id"),
                rs.getString("store_name"), rs.getString("sku_id"), rs.getString("product_name"),
                rs.getString("category"), rs.getString("action_type"), date(rs, "action_date"),
                rs.getString("timing_note"), rs.getObject("quantity", Integer.class), rs.getBigDecimal("markdown_pct"),
                rs.getString("counterpart_store_id"), rs.getString("counterpart_name"),
                rs.getBigDecimal("confidence"), rs.getBigDecimal("expected_waste_avoided_units"),
                rs.getBigDecimal("expected_lost_sales_avoided_units"), rs.getBigDecimal("expected_net_benefit"),
                rs.getString("effect_summary"), rs.getString("rationale"), rs.getString("status"),
                created == null ? null : created.toLocalDateTime());
    }

    private LocalDate latestRunDate() {
        List<LocalDate> rows = jdbc.sql("SELECT MAX(run_date) AS d FROM recommendations")
                .query((rs, i) -> date(rs, "d")).list();
        return rows.isEmpty() ? null : rows.get(0);
    }

    // -------------------------------------------------------------------- reads
    public List<RecommendationDto> list(String status, String storeId, String skuId, String actionType,
                                        LocalDate runDate) {
        LocalDate run = runDate != null ? runDate : latestRunDate();
        if (run == null) {
            return List.of();
        }
        StringBuilder sql = new StringBuilder(SELECT_REC).append(" WHERE r.run_date = :runDate");
        Map<String, Object> params = new HashMap<>();
        params.put("runDate", run);
        if (status != null) {
            sql.append(" AND r.status = :status");
            params.put("status", status);
        }
        if (storeId != null) {
            sql.append(" AND r.store_id = :storeId");
            params.put("storeId", storeId);
        }
        if (skuId != null) {
            sql.append(" AND r.sku_id = :skuId");
            params.put("skuId", skuId);
        }
        if (actionType != null) {
            sql.append(" AND r.action_type = :actionType");
            params.put("actionType", actionType);
        }
        sql.append(" ORDER BY r.expected_net_benefit DESC, r.rec_id");
        return jdbc.sql(sql.toString()).params(params).query((rs, i) -> mapRec(rs)).list();
    }

    public RecommendationDto get(long id) {
        return jdbc.sql(SELECT_REC + " WHERE r.rec_id = :id").param("id", id)
                .query((rs, i) -> mapRec(rs)).list().stream().findFirst()
                .orElseThrow(() -> new ResourceNotFoundException("Recommendation not found: " + id));
    }

    public RecommendationDetailDto detail(long id) {
        RecommendationDto rec = get(id);
        String evidence = jdbc.sql("SELECT evidence FROM recommendations WHERE rec_id = :id").param("id", id)
                .query((rs, i) -> rs.getString("evidence")).list().stream().findFirst().orElse(null);
        List<OptionDto> options = jdbc.sql("""
                SELECT agent, action_type, quantity, markdown_pct, counterpart_store_id, expected_net_benefit,
                       confidence, feasible, rule_notes, chosen
                FROM recommendation_options WHERE rec_id = :id
                ORDER BY chosen DESC, feasible DESC, expected_net_benefit DESC, option_id
                """).param("id", id).query((rs, i) -> new OptionDto(rs.getString("agent"),
                rs.getString("action_type"), rs.getObject("quantity", Integer.class), rs.getBigDecimal("markdown_pct"),
                rs.getString("counterpart_store_id"), rs.getBigDecimal("expected_net_benefit"),
                rs.getBigDecimal("confidence"), rs.getBoolean("feasible"), rs.getString("rule_notes"),
                rs.getBoolean("chosen"))).list();
        return new RecommendationDetailDto(rec, evidence, options, decisions(id));
    }

    public List<DecisionDto> decisions(Long recId) {
        String sql = "SELECT log_id, rec_id, decided_at, decided_by, decision, before_json, after_json, comment "
                + "FROM decision_log" + (recId != null ? " WHERE rec_id = :id" : "") + " ORDER BY log_id DESC";
        JdbcClient.StatementSpec spec = jdbc.sql(sql);
        if (recId != null) {
            spec = spec.param("id", recId);
        }
        return spec.query((rs, i) -> {
            Timestamp t = rs.getTimestamp("decided_at");
            return new DecisionDto(rs.getLong("log_id"), rs.getLong("rec_id"),
                    t == null ? null : t.toLocalDateTime(), rs.getString("decided_by"), rs.getString("decision"),
                    rs.getString("before_json"), rs.getString("after_json"), rs.getString("comment"));
        }).list();
    }

    public Map<String, Object> summary(LocalDate runDate) {
        LocalDate run = runDate != null ? runDate : latestRunDate();
        Map<String, Object> out = new LinkedHashMap<>();
        if (run == null) {
            out.put("runDate", null);
            return out;
        }
        out.put("runDate", run.toString());
        Map<String, Object> byStatus = new LinkedHashMap<>();
        jdbc.sql("SELECT status, COUNT(*) AS c FROM recommendations WHERE run_date = :d GROUP BY status ORDER BY status")
                .param("d", run).query((rs, i) -> {
                    byStatus.put(rs.getString("status"), rs.getInt("c"));
                    return rs.getString("status");
                }).list();
        out.put("byStatus", byStatus);
        Map<String, Object> byAction = new LinkedHashMap<>();
        jdbc.sql("""
                SELECT action_type, COUNT(*) AS c, COALESCE(SUM(expected_net_benefit), 0) AS benefit,
                       COALESCE(SUM(expected_waste_avoided_units), 0) AS waste
                FROM recommendations WHERE run_date = :d GROUP BY action_type ORDER BY action_type
                """).param("d", run).query((rs, i) -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("count", rs.getInt("c"));
            m.put("expectedNetBenefit", rs.getBigDecimal("benefit"));
            m.put("expectedWasteAvoidedUnits", rs.getBigDecimal("waste"));
            byAction.put(rs.getString("action_type"), m);
            return rs.getString("action_type");
        }).list();
        out.put("byAction", byAction);
        return out;
    }

    // ---------------------------------------------------------------- decisions
    @Transactional
    public RecommendationDto approve(long id, DecisionRequest req) {
        RecommendationDto rec = get(id);
        Map<String, Object> before = snapshot(rec);
        setStatus(id, "APPROVED", null, null);
        log(id, req.decidedBy(), "APPROVED", before, snapshot(get(id)), req.comment());
        return get(id);
    }

    @Transactional
    public RecommendationDto reject(long id, DecisionRequest req) {
        if (req.comment() == null || req.comment().isBlank()) {
            throw new IllegalArgumentException("A comment is required when rejecting a recommendation");
        }
        RecommendationDto rec = get(id);
        Map<String, Object> before = snapshot(rec);
        setStatus(id, "REJECTED", null, null);
        log(id, req.decidedBy(), "REJECTED", before, snapshot(get(id)), req.comment());
        return get(id);
    }

    @Transactional
    public RecommendationDto modify(long id, ModifyRequest req) {
        RecommendationDto rec = get(id);
        boolean markdown = rec.actionType().equals("MARKDOWN");
        if (req.quantity() == null && req.markdownPct() == null) {
            throw new IllegalArgumentException("Provide a new quantity or markdownPct");
        }
        if (markdown && req.quantity() != null) {
            throw new IllegalArgumentException("A markdown recommendation has no quantity; change markdownPct");
        }
        if (!markdown && req.markdownPct() != null) {
            throw new IllegalArgumentException("Only markdown recommendations have a markdownPct; change quantity");
        }
        if (req.quantity() != null) {
            if (req.quantity() <= 0) {
                throw new IllegalArgumentException("quantity must be greater than 0");
            }
            if (rec.actionType().equals("TRANSFER")) {
                Integer onHand = jdbc.sql("SELECT on_hand_qty FROM sku_risk WHERE run_date = :d AND store_id = :s AND sku_id = :k")
                        .param("d", rec.runDate()).param("s", rec.storeId()).param("k", rec.skuId())
                        .query((rs, i) -> rs.getInt("on_hand_qty")).list().stream().findFirst().orElse(null);
                if (onHand != null && req.quantity() > onHand) {
                    throw new IllegalArgumentException("Cannot transfer more than the " + onHand + " units on hand");
                }
            }
        }
        if (req.markdownPct() != null) {
            checkMarkdownRules(rec, req.markdownPct());
        }
        Map<String, Object> before = snapshot(rec);
        setStatus(id, "MODIFIED", req.quantity(), req.markdownPct());
        log(id, req.decidedBy(), "MODIFIED", before, snapshot(get(id)), req.comment());
        return get(id);
    }

    /** Planner changes must still respect the business rules. */
    private void checkMarkdownRules(RecommendationDto rec, BigDecimal pct) {
        double max = rules.number("max_markdown_pct", 50);
        if (pct.doubleValue() <= 0 || pct.doubleValue() > max) {
            throw new IllegalArgumentException("markdownPct must be above 0 and at most " + max + " (business rule)");
        }
        List<Double> price = jdbc.sql("""
                SELECT price FROM prices WHERE store_id = :s AND sku_id = :k AND effective_date <= :d
                ORDER BY effective_date DESC LIMIT 1
                """).param("s", rec.storeId()).param("k", rec.skuId()).param("d", rec.runDate())
                .query((rs, i) -> rs.getDouble("price")).list();
        List<Double> cost = jdbc.sql("SELECT cost FROM products WHERE sku_id = :k").param("k", rec.skuId())
                .query((rs, i) -> rs.getDouble("cost")).list();
        if (!price.isEmpty() && !cost.isEmpty()) {
            double newPrice = price.get(0) * (1 - pct.doubleValue() / 100);
            double floor = cost.get(0) * (1 + rules.number("min_price_over_cost_pct", 5) / 100);
            if (newPrice < floor) {
                throw new IllegalArgumentException(String.format(
                        "A %s%% markdown gives a price of %.2f, below the allowed floor of %.2f (business rule)",
                        pct.stripTrailingZeros().toPlainString(), newPrice, floor));
            }
        }
    }

    /** Only recommendations still in PROPOSED can be decided; the condition guards against double decisions. */
    private void setStatus(long id, String status, Integer quantity, BigDecimal markdownPct) {
        StringBuilder sql = new StringBuilder("UPDATE recommendations SET status = :status");
        Map<String, Object> params = new HashMap<>();
        params.put("status", status);
        params.put("id", id);
        if (quantity != null) {
            sql.append(", quantity = :quantity");
            params.put("quantity", quantity);
        }
        if (markdownPct != null) {
            sql.append(", markdown_pct = :markdownPct");
            params.put("markdownPct", markdownPct);
        }
        sql.append(" WHERE rec_id = :id AND status = 'PROPOSED'");
        if (jdbc.sql(sql.toString()).params(params).update() == 0) {
            throw new IllegalStateException("Recommendation " + id + " has already been decided");
        }
    }

    private void log(long id, String by, String decision, Map<String, Object> before,
                     Map<String, Object> after, String comment) {
        jdbc.sql("""
                INSERT INTO decision_log (rec_id, decided_by, decision, before_json, after_json, comment)
                VALUES (:id, :by, :decision, :before, :after, :comment)
                """).param("id", id).param("by", by.trim()).param("decision", decision)
                .param("before", toJson(before)).param("after", toJson(after))
                .param("comment", comment == null ? "" : comment.trim()).update();
    }

    private static Map<String, Object> snapshot(RecommendationDto r) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("status", r.status());
        m.put("actionType", r.actionType());
        m.put("quantity", r.quantity());
        m.put("markdownPct", r.markdownPct());
        m.put("counterpartStoreId", r.counterpartStoreId());
        return m;
    }

    private static String toJson(Map<String, Object> map) {
        StringBuilder sb = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, Object> e : map.entrySet()) {
            if (!first) {
                sb.append(',');
            }
            first = false;
            sb.append('"').append(escape(e.getKey())).append("\":");
            Object v = e.getValue();
            if (v == null) {
                sb.append("null");
            } else if (v instanceof BigDecimal bd) {
                sb.append(bd.toPlainString());
            } else if (v instanceof Number || v instanceof Boolean) {
                sb.append(v);
            } else {
                sb.append('"').append(escape(v.toString())).append('"');
            }
        }
        return sb.append('}').toString();
    }

    private static String escape(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t");
    }
}
