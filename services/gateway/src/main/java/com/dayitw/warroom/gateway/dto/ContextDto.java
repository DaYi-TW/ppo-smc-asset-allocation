package com.dayitw.warroom.gateway.dto;

import com.fasterxml.jackson.annotation.JsonAlias;

public record ContextDto(
        @JsonAlias("data_root") String dataRoot,
        @JsonAlias("include_smc") boolean includeSmc,
        @JsonAlias("n_warmup_steps") int nWarmupSteps,
        @JsonAlias("current_nav_at_as_of") double currentNavAtAsOf
) {}
