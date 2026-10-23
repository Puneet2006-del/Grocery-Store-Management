package com.zerowaste.grocery.dto;

import jakarta.validation.constraints.NotBlank;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

/** Request and response shapes for the planner workflow (recommendations, decisions, rules). */
public final class PlannerDtos {

    private PlannerDtos() {
    }

    public record RecommendationDto(long recId, LocalDate runDate, String storeId, String storeName,
                                    String skuId, String productName, String category,
                                    String actionType, LocalDate actionDate, String timingNote,
                                    Integer quantity, BigDecimal markdownPct,
                                    String counterpartStoreId, String counterpartStoreName,
                                    BigDecimal confidence, BigDecimal expectedWasteAvoidedUnits,
                                    BigDecimal expectedLostSalesAvoidedUnits, BigDecimal expectedNetBenefit,
                                    String effectSummary, String rationale, String status,
                                    LocalDateTime createdAt) {
    }

    /** One option an agent proposed, including those ruled out. */
    public record OptionDto(String agent, String actionType, Integer quantity, BigDecimal markdownPct,
                            String counterpartStoreId, BigDecimal expectedNetBenefit,
                            BigDecimal confidence, boolean feasible, String ruleNotes, boolean chosen) {
    }

    public record DecisionDto(long logId, long recId, LocalDateTime decidedAt, String decidedBy,
                              String decision, String beforeJson, String afterJson, String comment) {
    }

    /** evidence is the raw JSON text stored by the agents (forecast, risk, batches, options, rules). */
    public record RecommendationDetailDto(RecommendationDto recommendation, String evidence,
                                          List<OptionDto> options, List<DecisionDto> decisions) {
    }

    public record DecisionRequest(@NotBlank(message = "decidedBy is required") String decidedBy,
                                  String comment) {
    }

    public record ModifyRequest(@NotBlank(message = "decidedBy is required") String decidedBy,
                                String comment, Integer quantity, BigDecimal markdownPct) {
    }

    /** customised is true when this shopkeeper has changed the rule from the default. */
    public record RuleDto(String key, String value, String description, LocalDateTime updatedAt, boolean customised) {
    }

    public record RuleUpdateRequest(@NotBlank(message = "value is required") String value) {
    }
}
