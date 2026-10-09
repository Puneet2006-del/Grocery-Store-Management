package com.zerowaste.grocery.controller;

import com.zerowaste.grocery.dto.IntelligenceDtos.BatchRiskDto;
import com.zerowaste.grocery.dto.IntelligenceDtos.ForecastDto;
import com.zerowaste.grocery.dto.IntelligenceDtos.SkuRiskDto;
import com.zerowaste.grocery.service.IntelligenceService;
import com.zerowaste.grocery.util.Params;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Forecasts and risk assessments produced by the Milestone 2 intelligence layer. */
@RestController
@RequestMapping("/api")
public class IntelligenceController {

    private final IntelligenceService service;

    public IntelligenceController(IntelligenceService service) {
        this.service = service;
    }

    /** 7-day demand forecast with an 80% range. Defaults to the latest run. */
    @GetMapping("/forecasts")
    public List<ForecastDto> forecasts(
            @RequestParam(name = "storeId", required = false) String storeId,
            @RequestParam(name = "skuId", required = false) String skuId,
            @RequestParam(name = "runDate", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate runDate) {
        return service.forecasts(Params.id(storeId), Params.id(skuId), runDate);
    }

    /** Spoilage risk per batch, highest expected waste cost first. riskLevel: HIGH, MEDIUM or LOW. */
    @GetMapping("/risk/batches")
    public List<BatchRiskDto> batchRisk(
            @RequestParam(name = "storeId", required = false) String storeId,
            @RequestParam(name = "skuId", required = false) String skuId,
            @RequestParam(name = "riskLevel", required = false) String riskLevel,
            @RequestParam(name = "runDate", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate runDate) {
        return service.batchRisk(Params.id(storeId), Params.id(skuId), Params.id(riskLevel), runDate);
    }

    /** Stockout and excess-stock alerts per store and SKU. alertType: STOCKOUT_RISK, EXCESS_STOCK or OK. */
    @GetMapping("/risk/skus")
    public List<SkuRiskDto> skuRisk(
            @RequestParam(name = "storeId", required = false) String storeId,
            @RequestParam(name = "category", required = false) String category,
            @RequestParam(name = "alertType", required = false) String alertType,
            @RequestParam(name = "severity", required = false) String severity,
            @RequestParam(name = "runDate", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate runDate) {
        return service.skuRisk(Params.id(storeId), Params.text(category), Params.id(alertType),
                Params.id(severity), runDate);
    }

    /** Headline numbers: alert counts and expected waste. */
    @GetMapping("/risk/summary")
    public Map<String, Object> summary(
            @RequestParam(name = "runDate", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate runDate) {
        return service.summary(runDate);
    }
}
