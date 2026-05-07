package com.dayitw.warroom.gateway.controller;

import com.dayitw.warroom.gateway.dto.ErrorResponseDto;
import com.dayitw.warroom.gateway.dto.HealthDto;
import com.dayitw.warroom.gateway.dto.PredictionPayloadDto;
import com.dayitw.warroom.gateway.service.InferenceClient;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
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
@Tag(name = "Inference", description = "Proxy to 005 PPO inference service (REST pass-through)")
public class InferenceController {

    private static final Logger log = LoggerFactory.getLogger(InferenceController.class);
    private final InferenceClient inferenceClient;

    public InferenceController(InferenceClient inferenceClient) {
        this.inferenceClient = inferenceClient;
    }

    @PostMapping("/run")
    @Operation(
            summary = "觸發一次 PPO 推理",
            description = "Proxy POST /infer/run；timeout 90s（含 005 env warmup ~30s）。"
                    + "回應 camelCase；錯誤含 X-Request-Id header。")
    @ApiResponses({
            @ApiResponse(responseCode = "200",
                    description = "成功",
                    content = @Content(schema = @Schema(implementation = PredictionPayloadDto.class))),
            @ApiResponse(responseCode = "409", description = "005 mutex busy（InferenceBusy）",
                    content = @Content(schema = @Schema(implementation = ErrorResponseDto.class))),
            @ApiResponse(responseCode = "503", description = "005 不可達",
                    content = @Content(schema = @Schema(implementation = ErrorResponseDto.class))),
            @ApiResponse(responseCode = "504", description = "005 呼叫超過 90s",
                    content = @Content(schema = @Schema(implementation = ErrorResponseDto.class)))
    })
    public ResponseEntity<PredictionPayloadDto> run() {
        long start = System.currentTimeMillis();
        var payload = inferenceClient.runInference();
        log.info("event=inference.run.completed requestId={} durationMs={}",
                MDC.get("requestId"), System.currentTimeMillis() - start);
        return ResponseEntity.ok(payload);
    }

    @GetMapping("/latest")
    @Operation(
            summary = "取最新一筆 prediction（005 cache）",
            description = "Proxy GET /infer/latest；timeout 5s。")
    @ApiResponses({
            @ApiResponse(responseCode = "200",
                    content = @Content(schema = @Schema(implementation = PredictionPayloadDto.class))),
            @ApiResponse(responseCode = "404", description = "PredictionNotReady",
                    content = @Content(schema = @Schema(implementation = ErrorResponseDto.class))),
            @ApiResponse(responseCode = "503", description = "005 / Redis 不可達",
                    content = @Content(schema = @Schema(implementation = ErrorResponseDto.class)))
    })
    public ResponseEntity<PredictionPayloadDto> latest() {
        long start = System.currentTimeMillis();
        var payload = inferenceClient.getLatest();
        log.info("event=inference.latest.completed requestId={} durationMs={}",
                MDC.get("requestId"), System.currentTimeMillis() - start);
        return ResponseEntity.ok(payload);
    }

    @GetMapping("/healthz")
    @Operation(
            summary = "005 自身健康狀態（pass-through）",
            description = "與 /actuator/health 不同：本端點僅反映 005，不含 Gateway 自身狀態。")
    @ApiResponses({
            @ApiResponse(responseCode = "200",
                    content = @Content(schema = @Schema(implementation = HealthDto.class))),
            @ApiResponse(responseCode = "503", description = "005 degraded",
                    content = @Content(schema = @Schema(implementation = ErrorResponseDto.class)))
    })
    public ResponseEntity<HealthDto> healthz() {
        long start = System.currentTimeMillis();
        var payload = inferenceClient.getHealthz();
        log.info("event=inference.healthz.completed requestId={} durationMs={}",
                MDC.get("requestId"), System.currentTimeMillis() - start);
        return ResponseEntity.ok(payload);
    }
}
