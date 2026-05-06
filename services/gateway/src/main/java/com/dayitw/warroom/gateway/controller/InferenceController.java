package com.dayitw.warroom.gateway.controller;

import com.dayitw.warroom.gateway.dto.HealthDto;
import com.dayitw.warroom.gateway.dto.PredictionPayloadDto;
import com.dayitw.warroom.gateway.service.InferenceClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/inference")
public class InferenceController {

    private static final Logger log = LoggerFactory.getLogger(InferenceController.class);
    private final InferenceClient inferenceClient;

    public InferenceController(InferenceClient inferenceClient) {
        this.inferenceClient = inferenceClient;
    }

    @PostMapping("/run")
    public ResponseEntity<PredictionPayloadDto> run() {
        long start = System.currentTimeMillis();
        var payload = inferenceClient.runInference();
        log.info("event=inference.run.completed requestId={} durationMs={}",
                MDC.get("requestId"), System.currentTimeMillis() - start);
        return ResponseEntity.ok(payload);
    }

    @GetMapping("/latest")
    public ResponseEntity<PredictionPayloadDto> latest() {
        var payload = inferenceClient.getLatest();
        return ResponseEntity.ok(payload);
    }

    @GetMapping("/healthz")
    public ResponseEntity<HealthDto> healthz() {
        var payload = inferenceClient.getHealthz();
        return ResponseEntity.ok(payload);
    }
}
