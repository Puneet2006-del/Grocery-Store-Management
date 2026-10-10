package com.zerowaste.grocery.controller;

import com.zerowaste.grocery.dto.PlannerDtos.RuleDto;
import com.zerowaste.grocery.dto.PlannerDtos.RuleUpdateRequest;
import com.zerowaste.grocery.service.RuleService;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** View and edit the business rules. Changes apply the next time the agents run. */
@RestController
@RequestMapping("/api/rules")
public class RuleController {

    private final RuleService service;

    public RuleController(RuleService service) {
        this.service = service;
    }

    @GetMapping
    public List<RuleDto> all() {
        return service.all();
    }

    @PutMapping("/{key}")
    public RuleDto update(@PathVariable("key") String key, @Valid @RequestBody RuleUpdateRequest request) {
        return service.update(key, request.value());
    }
}
