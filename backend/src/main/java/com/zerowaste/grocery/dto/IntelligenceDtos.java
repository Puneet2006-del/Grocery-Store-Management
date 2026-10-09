package com.zerowaste.grocery.dto;

import java.math.BigDecimal;
import java.time.LocalDate;

/** Response shapes for the Milestone 2 intelligence tables (forecasts and risk). */
public final class IntelligenceDtos {

    private IntelligenceDtos() {
    }

    /** Demand forecast for one store, SKU and day, with an 80% range (lower = P10, upper = P90). */
    public record ForecastDto(LocalDate runDate, LocalDate forecastDate, int horizon,
                              String storeId, String storeName, String skuId, String productName,
                              BigDecimal predictedQty, BigDecimal lowerQty, BigDecimal upperQty,
                              String modelVersion) {
    }

    /** Spoilage risk for one batch. */
    public record BatchRiskDto(LocalDate runDate, String batchId, String storeId, String storeName,
                               String skuId, String productName, String category,
                               LocalDate expiryDate, int daysToExpiry, int qtyRemaining,
                               BigDecimal expectedSold, BigDecimal expectedUnsold, BigDecimal unsoldPct,
                               BigDecimal spoilageProb, BigDecimal expectedWasteCost, String riskLevel) {
    }

    /** Stockout and excess-stock assessment for one store and SKU. */
    public record SkuRiskDto(LocalDate runDate, String storeId, String storeName, String skuId,
                             String productName, String category, int onHandQty,
                             BigDecimal forecast7dQty, BigDecimal daysOfCover, LocalDate nextDeliveryDate,
                             BigDecimal stockoutProb, BigDecimal expectedShortfall,
                             BigDecimal expectedUnsold, BigDecimal excessPct,
                             BigDecimal expectedWasteCost, String alertType, String severity) {
    }
}
