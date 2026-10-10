package com.zerowaste.grocery.integration;

import com.zerowaste.grocery.dto.PlannerDtos.RecommendationDto;

/**
 * The three retail systems that act on approved recommendations.
 * Here they are simulated; a real deployment would replace the implementations with
 * calls to the retailer's ERP, warehouse management system and point-of-sale system.
 */
public final class RetailSystems {

    private RetailSystems() {
    }

    /** reference is the id the system gave the request (for example PO-12). */
    public record Response(boolean accepted, String reference, String message) {
    }

    /** ERP: purchase orders. */
    public interface Erp {
        Response submitOrder(RecommendationDto recommendation);
    }

    /** WMS: stock transfers between stores. */
    public interface Wms {
        Response submitTransfer(RecommendationDto recommendation);
    }

    /** POS: shelf price changes. */
    public interface Pos {
        Response submitPriceChange(RecommendationDto recommendation);
    }
}
