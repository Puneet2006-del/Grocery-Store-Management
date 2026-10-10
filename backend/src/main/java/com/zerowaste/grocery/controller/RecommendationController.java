package com.zerowaste.grocery.controller;

import com.zerowaste.grocery.dto.PlannerDtos.DecisionDto;
import com.zerowaste.grocery.dto.PlannerDtos.DecisionRequest;
import com.zerowaste.grocery.dto.PlannerDtos.ModifyRequest;
import com.zerowaste.grocery.dto.PlannerDtos.RecommendationDetailDto;
import com.zerowaste.grocery.dto.PlannerDtos.RecommendationDto;
import com.zerowaste.grocery.service.RecommendationService;
import com.zerowaste.grocery.util.Params;
import jakarta.validation.Valid;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Recommendations from the agents, and the planner's approve / modify / reject decisions. */
@RestController
@RequestMapping("/api")
public class RecommendationController {

    private final RecommendationService service;

    public RecommendationController(RecommendationService service) {
        this.service = service;
    }

    /** status: PROPOSED, APPROVED, MODIFIED, REJECTED. actionType: REPLENISH, MARKDOWN, TRANSFER. */
    @GetMapping("/recommendations")
    public List<RecommendationDto> list(
            @RequestParam(name = "status", required = false) String status,
            @RequestParam(name = "storeId", required = false) String storeId,
            @RequestParam(name = "skuId", required = false) String skuId,
            @RequestParam(name = "actionType", required = false) String actionType,
            @RequestParam(name = "runDate", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate runDate) {
        return service.list(Params.id(status), Params.id(storeId), Params.id(skuId), Params.id(actionType), runDate);
    }

    @GetMapping("/recommendations/summary")
    public Map<String, Object> summary(
            @RequestParam(name = "runDate", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate runDate) {
        return service.summary(runDate);
    }

    /** Full detail: evidence, every option the agents considered, and the decision history. */
    @GetMapping("/recommendations/{id}")
    public RecommendationDetailDto detail(@PathVariable("id") long id) {
        return service.detail(id);
    }

    @PostMapping("/recommendations/{id}/approve")
    public RecommendationDto approve(@PathVariable("id") long id, @Valid @RequestBody DecisionRequest request) {
        return service.approve(id, request);
    }

    /** A comment is required. */
    @PostMapping("/recommendations/{id}/reject")
    public RecommendationDto reject(@PathVariable("id") long id, @Valid @RequestBody DecisionRequest request) {
        return service.reject(id, request);
    }

    /** Change quantity (replenish, transfer) or markdownPct (markdown). Business rules still apply. */
    @PostMapping("/recommendations/{id}/modify")
    public RecommendationDto modify(@PathVariable("id") long id, @Valid @RequestBody ModifyRequest request) {
        return service.modify(id, request);
    }

    /** Decision history, newest first. Optional recId filter. */
    @GetMapping("/decisions")
    public List<DecisionDto> decisions(@RequestParam(name = "recId", required = false) Long recId) {
        return service.decisions(recId);
    }
}
