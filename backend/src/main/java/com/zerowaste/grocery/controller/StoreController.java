package com.zerowaste.grocery.controller;

import com.zerowaste.grocery.dto.Dtos.StoreDto;
import com.zerowaste.grocery.dto.ShopDtos.CreateShopRequest;
import com.zerowaste.grocery.exception.ResourceNotFoundException;
import com.zerowaste.grocery.repository.StoreRepository;
import com.zerowaste.grocery.service.AccessService;
import com.zerowaste.grocery.service.ShopService;
import com.zerowaste.grocery.util.Params;
import jakarta.validation.Valid;
import java.util.Comparator;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** The signed-in shopkeeper's own shops. */
@RestController
@RequestMapping("/api/stores")
public class StoreController {

    private final StoreRepository repository;
    private final AccessService access;
    private final ShopService shops;

    public StoreController(StoreRepository repository, AccessService access, ShopService shops) {
        this.repository = repository;
        this.access = access;
        this.shops = shops;
    }

    @GetMapping
    public List<StoreDto> all() {
        return repository.findAllById(access.storeIds()).stream()
                .sorted(Comparator.comparing(s -> s.getStoreId()))
                .map(StoreDto::from).toList();
    }

    /** Add a shop. Its history and forecasts are created in the background; poll GET /api/stores for the status. */
    @PostMapping
    public StoreDto create(@Valid @RequestBody CreateShopRequest request) {
        return shops.create(request);
    }

    /** Try the set-up again for a shop whose status is FAILED. */
    @PostMapping("/{storeId}/retry")
    public StoreDto retry(@PathVariable("storeId") String storeId) {
        return shops.retry(Params.id(storeId));
    }

    @GetMapping("/{storeId}")
    public StoreDto one(@PathVariable("storeId") String storeId) {
        String id = Params.id(storeId);
        access.requireStore(id);
        return repository.findById(id).map(StoreDto::from)
                .orElseThrow(() -> new ResourceNotFoundException("Store not found: " + storeId));
    }
}
