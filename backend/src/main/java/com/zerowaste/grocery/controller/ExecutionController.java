package com.zerowaste.grocery.controller;

import com.zerowaste.grocery.dto.ExecutionDtos.ErpOrderDto;
import com.zerowaste.grocery.dto.ExecutionDtos.ExecuteRequest;
import com.zerowaste.grocery.dto.ExecutionDtos.ExecutionResultDto;
import com.zerowaste.grocery.dto.ExecutionDtos.FeedbackDto;
import com.zerowaste.grocery.dto.ExecutionDtos.FeedbackRequest;
import com.zerowaste.grocery.dto.ExecutionDtos.PosPriceChangeDto;
import com.zerowaste.grocery.dto.ExecutionDtos.WmsTransferDto;
import com.zerowaste.grocery.service.ExecutionService;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Execute approved recommendations in the simulated systems, and record outcomes. */
@RestController
@RequestMapping("/api")
public class ExecutionController {

    private final ExecutionService service;

    public ExecutionController(ExecutionService service) {
        this.service = service;
    }

    /** Sends an APPROVED or MODIFIED recommendation to the ERP (orders), WMS (transfers) or POS (prices). */
    @PostMapping("/recommendations/{id}/execute")
    public ExecutionResultDto execute(@PathVariable("id") long id, @Valid @RequestBody ExecuteRequest request) {
        return service.execute(id, request.executedBy());
    }

    /** Record the real outcome of an executed recommendation (waste, lost sales, rating, comment). */
    @PostMapping("/recommendations/{id}/feedback")
    public FeedbackDto addFeedback(@PathVariable("id") long id, @RequestBody FeedbackRequest request) {
        return service.addFeedback(id, request);
    }

    @GetMapping("/feedback")
    public List<FeedbackDto> feedback(@RequestParam(name = "recId", required = false) Long recId) {
        return service.feedback(recId);
    }

    @GetMapping("/sim/erp/orders")
    public List<ErpOrderDto> erpOrders(@RequestParam(name = "recId", required = false) Long recId) {
        return service.erpOrders(recId);
    }

    @GetMapping("/sim/wms/transfers")
    public List<WmsTransferDto> wmsTransfers(@RequestParam(name = "recId", required = false) Long recId) {
        return service.wmsTransfers(recId);
    }

    @GetMapping("/sim/pos/price-changes")
    public List<PosPriceChangeDto> posPriceChanges(@RequestParam(name = "recId", required = false) Long recId) {
        return service.posPriceChanges(recId);
    }
}
