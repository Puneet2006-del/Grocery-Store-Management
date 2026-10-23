package com.zerowaste.grocery.controller;

import com.zerowaste.grocery.dto.Dtos.PageResponse;
import com.zerowaste.grocery.dto.Dtos.SaleDto;
import com.zerowaste.grocery.repository.SaleRepository;
import com.zerowaste.grocery.service.AccessService;
import com.zerowaste.grocery.util.Params;
import java.time.LocalDate;
import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/sales")
public class SaleController {

    private static final LocalDate MIN_DATE = LocalDate.of(1900, 1, 1);
    private static final LocalDate MAX_DATE = LocalDate.of(2999, 12, 31);

    private final SaleRepository repository;
    private final AccessService access;

    public SaleController(SaleRepository repository, AccessService access) {
        this.repository = repository;
        this.access = access;
    }

    /** Paginated sales history, newest first. All filters are optional. */
    @GetMapping
    public PageResponse<SaleDto> sales(
            @RequestParam(name = "storeId", required = false) String storeId,
            @RequestParam(name = "skuId", required = false) String skuId,
            @RequestParam(name = "from", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate from,
            @RequestParam(name = "to", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate to,
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "size", defaultValue = "50") int size) {
        int safePage = Math.max(page, 0);
        int safeSize = Math.min(Math.max(size, 1), 500);
        LocalDate fromDate = from != null ? from : MIN_DATE;
        LocalDate toDate = to != null ? to : MAX_DATE;
        if (fromDate.isAfter(toDate)) {
            throw new IllegalArgumentException("'from' must not be after 'to'");
        }
        String id = Params.id(storeId);
        List<String> ids;
        if (id != null) {
            access.requireStore(id);
            ids = List.of(id);
        } else {
            ids = access.storeIds();
        }
        if (ids.isEmpty()) {
            return new PageResponse<>(List.of(), safePage, safeSize, 0, 0);
        }
        return PageResponse.of(
                repository.search(ids, Params.id(skuId), fromDate, toDate, PageRequest.of(safePage, safeSize))
                        .map(SaleDto::from));
    }
}
