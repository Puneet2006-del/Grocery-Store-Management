package com.zerowaste.grocery.dto;

import jakarta.validation.constraints.NotBlank;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

/** Request and response shapes for executing approved actions and recording feedback. */
public final class ExecutionDtos {

    private ExecutionDtos() {
    }

    public record ExecuteRequest(@NotBlank(message = "executedBy is required") String executedBy) {
    }

    /** What the simulated retail system answered. */
    public record ExecutionResultDto(long recId, String system, boolean accepted, String reference,
                                     String message, String status) {
    }

    public record FeedbackRequest(Integer plannerRating, BigDecimal actualWasteUnits,
                                  BigDecimal actualLostSalesUnits, String comment) {
    }

    public record FeedbackDto(long feedbackId, long recId, LocalDateTime recordedAt, String outcome,
                              BigDecimal actualWasteUnits, BigDecimal actualLostSalesUnits,
                              Integer plannerRating, String comment) {
    }

    public record ErpOrderDto(long poId, long recId, String storeId, String skuId, int qty,
                              LocalDate orderDate, LocalDate expectedDeliveryDate, String status,
                              String responseMessage, LocalDateTime createdAt) {
    }

    public record WmsTransferDto(long transferId, long recId, String fromStoreId, String toStoreId,
                                 String skuId, int qty, String status, String responseMessage,
                                 LocalDateTime createdAt) {
    }

    public record PosPriceChangeDto(long changeId, long recId, String storeId, String skuId,
                                    BigDecimal markdownPct, BigDecimal newPrice, LocalDate effectiveDate,
                                    String status, String responseMessage, LocalDateTime createdAt) {
    }
}
