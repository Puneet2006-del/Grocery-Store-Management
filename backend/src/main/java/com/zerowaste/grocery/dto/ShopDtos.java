package com.zerowaste.grocery.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

/** Request shape for adding a shop. */
public final class ShopDtos {

    private ShopDtos() {
    }

    /** type: urban or suburban. size: small, medium or large. */
    public record CreateShopRequest(@NotBlank(message = "name is required") String name,
                                    @NotBlank(message = "city is required") String city,
                                    @NotBlank(message = "type is required") String type,
                                    @NotBlank(message = "size is required") String size,
                                    @NotNull(message = "latitude is required") Double latitude,
                                    @NotNull(message = "longitude is required") Double longitude) {
    }
}
