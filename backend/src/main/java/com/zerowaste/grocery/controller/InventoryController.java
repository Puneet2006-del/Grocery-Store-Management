package com.zerowaste.grocery.controller;

import com.zerowaste.grocery.dto.Dtos.BatchItem;
import com.zerowaste.grocery.dto.Dtos.InventorySummaryItem;
import com.zerowaste.grocery.service.InventoryService;
import com.zerowaste.grocery.util.Params;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class InventoryController {

    private final InventoryService service;

    public InventoryController(InventoryService service) {
        this.service = service;
    }

    /** Batch-level inventory with expiry dates and days to expiry. */
    @GetMapping("/inventory")
    public List<BatchItem> inventory(
            @RequestParam(name = "storeId", required = false) String storeId,
            @RequestParam(name = "skuId", required = false) String skuId,
            @RequestParam(name = "category", required = false) String category,
            @RequestParam(name = "asOf", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate asOf) {
        return service.batchItems(Params.id(storeId), Params.id(skuId), Params.text(category), asOf);
    }

    /** One row per store and SKU: on-hand quantity, nearest expiry, status. */
    @GetMapping("/inventory/summary")
    public List<InventorySummaryItem> summary(
            @RequestParam(name = "storeId", required = false) String storeId,
            @RequestParam(name = "category", required = false) String category,
            @RequestParam(name = "asOf", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate asOf) {
        return service.summary(Params.id(storeId), Params.text(category), asOf);
    }

    /** The simulated "today" that days-to-expiry is measured from. */
    @GetMapping("/meta")
    public Map<String, Object> meta() {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("asOfDate", service.defaultAsOf().toString());
        body.put("note", "Simulated data; days to expiry are measured from asOfDate.");
        return body;
    }
}
