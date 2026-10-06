package com.zerowaste.grocery.controller;

import com.zerowaste.grocery.dto.Dtos.StoreDto;
import com.zerowaste.grocery.exception.ResourceNotFoundException;
import com.zerowaste.grocery.repository.StoreRepository;
import com.zerowaste.grocery.util.Params;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/stores")
public class StoreController {

    private final StoreRepository repository;

    public StoreController(StoreRepository repository) {
        this.repository = repository;
    }

    @GetMapping
    public List<StoreDto> all() {
        return repository.findAll(Sort.by("storeId")).stream().map(StoreDto::from).toList();
    }

    @GetMapping("/{storeId}")
    public StoreDto one(@PathVariable("storeId") String storeId) {
        String id = Params.id(storeId);
        return repository.findById(id == null ? "" : id)
                .map(StoreDto::from)
                .orElseThrow(() -> new ResourceNotFoundException("Store not found: " + storeId));
    }
}
