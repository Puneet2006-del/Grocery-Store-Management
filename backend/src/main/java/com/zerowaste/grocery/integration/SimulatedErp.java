package com.zerowaste.grocery.integration;

import com.zerowaste.grocery.dto.PlannerDtos.RecommendationDto;
import com.zerowaste.grocery.integration.RetailSystems.Response;
import com.zerowaste.grocery.service.RuleService;
import java.time.LocalDate;
import javax.sql.DataSource;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

/** Simulated ERP. Rounds orders up to the pack size, as a real ERP would, and logs every request. */
@Component
public class SimulatedErp implements RetailSystems.Erp {

    private final JdbcClient jdbc;
    private final RuleService rules;

    public SimulatedErp(DataSource dataSource, RuleService rules) {
        this.jdbc = JdbcClient.create(dataSource);
        this.rules = rules;
    }

    @Override
    public Response submitOrder(RecommendationDto rec) {
        int requested = rec.quantity() == null ? 0 : rec.quantity();
        LocalDate delivery = rec.actionDate().plusDays(1);
        if (requested <= 0) {
            record(rec, requested, delivery, "REJECTED", "Order quantity must be greater than zero");
            return new Response(false, null, "ERP rejected the order: quantity must be greater than zero");
        }
        int pack = Math.max(1, (int) rules.number("order_pack_size", 5));
        int ordered = (int) (Math.ceil(requested / (double) pack) * pack);
        String message = ordered == requested
                ? "Purchase order accepted"
                : "Purchase order accepted; quantity rounded up from " + requested + " to " + ordered
                + " to fit the pack size of " + pack;
        long id = record(rec, ordered, delivery, "ACCEPTED", message);
        return new Response(true, "PO-" + id, message + ". Expected delivery " + delivery);
    }

    private long record(RecommendationDto rec, int qty, LocalDate delivery, String status, String message) {
        jdbc.sql("""
                INSERT INTO sim_erp_orders (rec_id, store_id, sku_id, qty, order_date, expected_delivery_date,
                                            status, response_message)
                VALUES (:rec, :store, :sku, :qty, :orderDate, :delivery, :status, :message)
                """).param("rec", rec.recId()).param("store", rec.storeId()).param("sku", rec.skuId())
                .param("qty", qty).param("orderDate", rec.actionDate()).param("delivery", delivery)
                .param("status", status).param("message", message).update();
        return jdbc.sql("SELECT MAX(po_id) AS id FROM sim_erp_orders WHERE rec_id = :rec")
                .param("rec", rec.recId()).query((rs, i) -> rs.getLong("id")).list().get(0);
    }
}
