package com.zerowaste.grocery.service;

import com.zerowaste.grocery.dto.ExecutionDtos.ErpOrderDto;
import com.zerowaste.grocery.dto.ExecutionDtos.ExecutionResultDto;
import com.zerowaste.grocery.dto.ExecutionDtos.FeedbackDto;
import com.zerowaste.grocery.dto.ExecutionDtos.FeedbackRequest;
import com.zerowaste.grocery.dto.ExecutionDtos.PosPriceChangeDto;
import com.zerowaste.grocery.dto.ExecutionDtos.WmsTransferDto;
import com.zerowaste.grocery.dto.PlannerDtos.RecommendationDto;
import com.zerowaste.grocery.integration.RetailSystems;
import com.zerowaste.grocery.integration.RetailSystems.Response;
import java.math.BigDecimal;
import java.sql.Date;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import javax.sql.DataSource;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Sends approved recommendations to the simulated ERP, WMS or POS, records what happened in the
 * decision log and feedback log, and lets planners record the real outcome afterwards.
 */
@Service
public class ExecutionService {

    private final JdbcClient jdbc;
    private final RecommendationService recommendations;
    private final RetailSystems.Erp erp;
    private final RetailSystems.Wms wms;
    private final RetailSystems.Pos pos;

    public ExecutionService(DataSource dataSource, RecommendationService recommendations,
                            RetailSystems.Erp erp, RetailSystems.Wms wms, RetailSystems.Pos pos) {
        this.jdbc = JdbcClient.create(dataSource);
        this.recommendations = recommendations;
        this.erp = erp;
        this.wms = wms;
        this.pos = pos;
    }

    // ---------------------------------------------------------------- execution
    @Transactional
    public ExecutionResultDto execute(long id, String executedBy) {
        RecommendationDto rec = recommendations.get(id);
        String status = rec.status();
        if (status.equals("PROPOSED")) {
            if (requiresApproval()) {
                throw new IllegalStateException("Recommendation " + id
                        + " must be approved by a planner before it can be executed");
            }
            jdbc.sql("UPDATE recommendations SET status = 'APPROVED' WHERE rec_id = :id AND status = 'PROPOSED'")
                    .param("id", id).update();
            logDecision(id, "system", "APPROVED", "PROPOSED", "APPROVED", "Auto-approved: planner approval is switched off");
            status = "APPROVED";
        }
        if (!status.equals("APPROVED") && !status.equals("MODIFIED")) {
            throw new IllegalStateException("Recommendation " + id + " is " + status + " and cannot be executed");
        }

        String system;
        Response response;
        switch (rec.actionType()) {
            case "REPLENISH" -> {
                system = "ERP";
                response = erp.submitOrder(rec);
            }
            case "TRANSFER" -> {
                system = "WMS";
                response = wms.submitTransfer(rec);
            }
            case "MARKDOWN" -> {
                system = "POS";
                response = pos.submitPriceChange(rec);
            }
            default -> throw new IllegalStateException("Unknown action type: " + rec.actionType());
        }

        if (response.accepted()) {
            int n = jdbc.sql("UPDATE recommendations SET status = 'EXECUTED' WHERE rec_id = :id AND status IN ('APPROVED','MODIFIED')")
                    .param("id", id).update();
            if (n == 0) {
                throw new IllegalStateException("Recommendation " + id + " was changed by someone else");
            }
            logDecision(id, executedBy, "EXECUTED", status, "EXECUTED", system + " " + response.reference() + ": " + response.message());
            logFeedback(id, "EXECUTED", system + " " + response.reference() + ": " + response.message());
            return new ExecutionResultDto(id, system, true, response.reference(), response.message(), "EXECUTED");
        }
        logDecision(id, executedBy, "EXEC_FAILED", status, status, response.message());
        logFeedback(id, "FAILED", response.message());
        return new ExecutionResultDto(id, system, false, null, response.message(), status);
    }

    private boolean requiresApproval() {
        List<String> v = jdbc.sql("SELECT rule_value FROM business_rules WHERE rule_key = 'require_planner_approval'")
                .query((rs, i) -> rs.getString("rule_value")).list();
        return v.isEmpty() || !v.get(0).trim().equalsIgnoreCase("false");
    }

    private void logDecision(long id, String by, String decision, String beforeStatus, String afterStatus, String comment) {
        jdbc.sql("""
                INSERT INTO decision_log (rec_id, decided_by, decision, before_json, after_json, comment)
                VALUES (:id, :by, :decision, :before, :after, :comment)
                """).param("id", id).param("by", by.trim()).param("decision", decision)
                .param("before", "{\"status\":\"" + beforeStatus + "\"}")
                .param("after", "{\"status\":\"" + afterStatus + "\"}")
                .param("comment", comment == null ? "" : comment).update();
    }

    private void logFeedback(long id, String outcome, String comment) {
        jdbc.sql("INSERT INTO feedback_log (rec_id, outcome, comment) VALUES (:id, :outcome, :comment)")
                .param("id", id).param("outcome", outcome).param("comment", comment).update();
    }

    // ----------------------------------------------------------------- feedback
    @Transactional
    public FeedbackDto addFeedback(long id, FeedbackRequest req) {
        RecommendationDto rec = recommendations.get(id);
        if (!rec.status().equals("EXECUTED")) {
            throw new IllegalStateException("Feedback can only be recorded for executed recommendations (this one is "
                    + rec.status() + ")");
        }
        if (req.plannerRating() == null && req.actualWasteUnits() == null
                && req.actualLostSalesUnits() == null && (req.comment() == null || req.comment().isBlank())) {
            throw new IllegalArgumentException("Provide at least one of plannerRating, actualWasteUnits, actualLostSalesUnits or comment");
        }
        if (req.plannerRating() != null && (req.plannerRating() < 1 || req.plannerRating() > 5)) {
            throw new IllegalArgumentException("plannerRating must be between 1 and 5");
        }
        if ((req.actualWasteUnits() != null && req.actualWasteUnits().signum() < 0)
                || (req.actualLostSalesUnits() != null && req.actualLostSalesUnits().signum() < 0)) {
            throw new IllegalArgumentException("Actual units must not be negative");
        }
        jdbc.sql("""
                INSERT INTO feedback_log (rec_id, outcome, actual_waste_units, actual_lost_sales_units,
                                          planner_rating, comment)
                VALUES (:id, 'OBSERVED', :waste, :lost, :rating, :comment)
                """).param("id", id).param("waste", req.actualWasteUnits()).param("lost", req.actualLostSalesUnits())
                .param("rating", req.plannerRating()).param("comment", req.comment() == null ? "" : req.comment().trim())
                .update();
        return feedback(id).get(0);
    }

    public List<FeedbackDto> feedback(Long recId) {
        String sql = "SELECT feedback_id, rec_id, recorded_at, outcome, actual_waste_units, actual_lost_sales_units, "
                + "planner_rating, comment FROM feedback_log" + (recId != null ? " WHERE rec_id = :id" : "")
                + " ORDER BY feedback_id DESC";
        JdbcClient.StatementSpec spec = jdbc.sql(sql);
        if (recId != null) {
            spec = spec.param("id", recId);
        }
        return spec.query((rs, i) -> new FeedbackDto(rs.getLong("feedback_id"), rs.getLong("rec_id"),
                ts(rs, "recorded_at"), rs.getString("outcome"), rs.getBigDecimal("actual_waste_units"),
                rs.getBigDecimal("actual_lost_sales_units"), rs.getObject("planner_rating", Integer.class),
                rs.getString("comment"))).list();
    }

    // ------------------------------------------- what the simulated systems received
    public List<ErpOrderDto> erpOrders(Long recId) {
        return jdbc.sql("SELECT po_id, rec_id, store_id, sku_id, qty, order_date, expected_delivery_date, status, "
                        + "response_message, created_at FROM sim_erp_orders" + where(recId) + " ORDER BY po_id DESC")
                .params(recParam(recId)).query((rs, i) -> new ErpOrderDto(rs.getLong("po_id"), rs.getLong("rec_id"),
                        rs.getString("store_id"), rs.getString("sku_id"), rs.getInt("qty"), date(rs, "order_date"),
                        date(rs, "expected_delivery_date"), rs.getString("status"), rs.getString("response_message"),
                        ts(rs, "created_at"))).list();
    }

    public List<WmsTransferDto> wmsTransfers(Long recId) {
        return jdbc.sql("SELECT transfer_id, rec_id, from_store_id, to_store_id, sku_id, qty, status, response_message, "
                        + "created_at FROM sim_wms_transfers" + where(recId) + " ORDER BY transfer_id DESC")
                .params(recParam(recId)).query((rs, i) -> new WmsTransferDto(rs.getLong("transfer_id"),
                        rs.getLong("rec_id"), rs.getString("from_store_id"), rs.getString("to_store_id"),
                        rs.getString("sku_id"), rs.getInt("qty"), rs.getString("status"),
                        rs.getString("response_message"), ts(rs, "created_at"))).list();
    }

    public List<PosPriceChangeDto> posPriceChanges(Long recId) {
        return jdbc.sql("SELECT change_id, rec_id, store_id, sku_id, markdown_pct, new_price, effective_date, status, "
                        + "response_message, created_at FROM sim_pos_price_changes" + where(recId) + " ORDER BY change_id DESC")
                .params(recParam(recId)).query((rs, i) -> new PosPriceChangeDto(rs.getLong("change_id"),
                        rs.getLong("rec_id"), rs.getString("store_id"), rs.getString("sku_id"),
                        rs.getBigDecimal("markdown_pct"), rs.getBigDecimal("new_price"), date(rs, "effective_date"),
                        rs.getString("status"), rs.getString("response_message"), ts(rs, "created_at"))).list();
    }

    private static String where(Long recId) {
        return recId == null ? "" : " WHERE rec_id = :recId";
    }

    private static java.util.Map<String, Object> recParam(Long recId) {
        return recId == null ? java.util.Map.of() : java.util.Map.of("recId", recId);
    }

    private static LocalDate date(ResultSet rs, String col) throws SQLException {
        Date d = rs.getDate(col);
        return d == null ? null : d.toLocalDate();
    }

    private static LocalDateTime ts(ResultSet rs, String col) throws SQLException {
        Timestamp t = rs.getTimestamp(col);
        return t == null ? null : t.toLocalDateTime();
    }
}
