package com.dayitw.warroom.gateway.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("inference")
public class InferenceHealthIndicator implements HealthIndicator {

    private final InferenceClient inferenceClient;
    private final String baseUrl;

    public InferenceHealthIndicator(InferenceClient inferenceClient,
                                    @Value("${inference.url}") String baseUrl) {
        this.inferenceClient = inferenceClient;
        this.baseUrl = baseUrl;
    }

    @Override
    public Health health() {
        long start = System.currentTimeMillis();
        try {
            inferenceClient.getHealthz();
            long latency = System.currentTimeMillis() - start;
            return Health.up().withDetail("url", baseUrl).withDetail("latencyMs", latency).build();
        } catch (Exception ex) {
            return Health.down()
                    .withDetail("url", baseUrl)
                    .withDetail("error", ex.getClass().getSimpleName() + ": " + ex.getMessage())
                    .build();
        }
    }
}
