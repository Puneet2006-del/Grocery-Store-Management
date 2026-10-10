package com.zerowaste.grocery.integration;

import com.zerowaste.grocery.dto.PlannerDtos.RecommendationDto;
import com.zerowaste.grocery.integration.RetailSystems.Response;
import java.util.List;
import javax.sql.DataSource;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

/** Simulated warehouse management system. Accepts a transfer only if the source store has the stock. */
@Component
public class SimulatedWms implements RetailSystems.Wms {

    private final JdbcClient jdbc;

    public SimulatedWms(DataSource dataSource) {
        this.jdbc = JdbcClient.create(dataSource);
    }

    @Override
    public Response submitTransfer(RecommendationDto rec) {
        int qty = rec.quantity() == null ? 0 : rec.quantity();
        String to = rec.counterpartStoreId();
        String problem = null;
        if (to == null || to.equals(rec.storeId())) {
            problem = "Destination store is missing or the same as the source";
        } else if (qty <= 0) {
            problem = "Transfer quantity must be greater than zero";
        } else {
            List<Integer> onHand = jdbc.sql("SELECT on_hand_qty FROM sku_risk WHERE run_date = :d AND store_id = :s AND sku_id = :k")
                    .param("d", rec.runDate()).param("s", rec.storeId()).param("k", rec.skuId())
                    .query((rs, i) -> rs.getInt("on_hand_qty")).list();
            if (!onHand.isEmpty() && qty > onHand.get(0)) {
                problem = "Source store has only " + onHand.get(0) + " units on hand, cannot move " + qty;
            }
        }
        String message = problem == null ? "Transfer accepted and scheduled for dispatch" : problem;
        jdbc.sql("""
                INSERT INTO sim_wms_transfers (rec_id, from_store_id, to_store_id, sku_id, qty, status, response_message)
                VALUES (:rec, :from, :to, :sku, :qty, :status, :message)
                """).param("rec", rec.recId()).param("from", rec.storeId()).param("to", to == null ? "" : to)
                .param("sku", rec.skuId()).param("qty", qty).param("status", problem == null ? "ACCEPTED" : "REJECTED")
                .param("message", message).update();
        if (problem != null) {
            return new Response(false, null, "WMS rejected the transfer: " + problem);
        }
        long id = jdbc.sql("SELECT MAX(transfer_id) AS id FROM sim_wms_transfers WHERE rec_id = :rec")
                .param("rec", rec.recId()).query((rs, i) -> rs.getLong("id")).list().get(0);
        return new Response(true, "TR-" + id, message + " (" + qty + " units to " + to + ")");
    }
}
