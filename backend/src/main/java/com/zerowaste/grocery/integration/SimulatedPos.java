package com.zerowaste.grocery.integration;

import com.zerowaste.grocery.dto.PlannerDtos.RecommendationDto;
import com.zerowaste.grocery.integration.RetailSystems.Response;
import com.zerowaste.grocery.service.RuleService;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import javax.sql.DataSource;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

/** Simulated point-of-sale system. Applies the markdown to the shelf price unless it breaks the price floor. */
@Component
public class SimulatedPos implements RetailSystems.Pos {

    private final JdbcClient jdbc;
    private final RuleService rules;

    public SimulatedPos(DataSource dataSource, RuleService rules) {
        this.jdbc = JdbcClient.create(dataSource);
        this.rules = rules;
    }

    @Override
    public Response submitPriceChange(RecommendationDto rec) {
        BigDecimal pct = rec.markdownPct() == null ? BigDecimal.ZERO : rec.markdownPct();
        List<Double> price = jdbc.sql("""
                SELECT price FROM prices WHERE store_id = :s AND sku_id = :k AND effective_date <= :d
                ORDER BY effective_date DESC LIMIT 1
                """).param("s", rec.storeId()).param("k", rec.skuId()).param("d", rec.runDate())
                .query((rs, i) -> rs.getDouble("price")).list();
        List<Double> cost = jdbc.sql("SELECT cost FROM products WHERE sku_id = :k").param("k", rec.skuId())
                .query((rs, i) -> rs.getDouble("cost")).list();
        double current = price.isEmpty() ? 0 : price.get(0);
        BigDecimal newPrice = BigDecimal.valueOf(current * (1 - pct.doubleValue() / 100)).setScale(2, RoundingMode.HALF_UP);

        String problem = null;
        if (price.isEmpty()) {
            problem = "No current shelf price found for this store and SKU";
        } else if (pct.doubleValue() <= 0 || pct.doubleValue() >= 100) {
            problem = "Markdown must be between 0% and 100%";
        } else if (!cost.isEmpty()) {
            double floor = cost.get(0) * (1 + rules.number("min_price_over_cost_pct", 5) / 100);
            if (newPrice.doubleValue() < floor) {
                problem = String.format("New price %.2f is below the price floor %.2f", newPrice.doubleValue(), floor);
            }
        }
        String message = problem == null
                ? String.format("Price change accepted: %.2f to %.2f", current, newPrice.doubleValue())
                : problem;
        jdbc.sql("""
                INSERT INTO sim_pos_price_changes (rec_id, store_id, sku_id, markdown_pct, new_price,
                                                   effective_date, status, response_message)
                VALUES (:rec, :store, :sku, :pct, :price, :eff, :status, :message)
                """).param("rec", rec.recId()).param("store", rec.storeId()).param("sku", rec.skuId())
                .param("pct", pct).param("price", newPrice).param("eff", rec.actionDate())
                .param("status", problem == null ? "ACCEPTED" : "REJECTED").param("message", message).update();
        if (problem != null) {
            return new Response(false, null, "POS rejected the price change: " + problem);
        }
        long id = jdbc.sql("SELECT MAX(change_id) AS id FROM sim_pos_price_changes WHERE rec_id = :rec")
                .param("rec", rec.recId()).query((rs, i) -> rs.getLong("id")).list().get(0);
        return new Response(true, "PX-" + id, message + ", effective " + rec.actionDate());
    }
}
