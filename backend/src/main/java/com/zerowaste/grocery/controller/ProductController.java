package com.zerowaste.grocery.controller;

import com.zerowaste.grocery.dto.Dtos.ProductDto;
import com.zerowaste.grocery.entity.Product;
import com.zerowaste.grocery.exception.ResourceNotFoundException;
import com.zerowaste.grocery.repository.ProductRepository;
import com.zerowaste.grocery.util.Params;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductRepository repository;

    public ProductController(ProductRepository repository) {
        this.repository = repository;
    }

    @GetMapping
    public List<ProductDto> all(@RequestParam(name = "category", required = false) String category) {
        String cat = Params.text(category);
        List<Product> products = cat == null
                ? repository.findAllByOrderBySkuIdAsc()
                : repository.findByCategoryIgnoreCaseOrderBySkuIdAsc(cat);
        return products.stream().map(ProductDto::from).toList();
    }

    @GetMapping("/{skuId}")
    public ProductDto one(@PathVariable("skuId") String skuId) {
        String id = Params.id(skuId);
        return repository.findById(id == null ? "" : id)
                .map(ProductDto::from)
                .orElseThrow(() -> new ResourceNotFoundException("Product not found: " + skuId));
    }
}
