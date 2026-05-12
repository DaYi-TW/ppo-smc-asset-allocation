package com.dayitw.warroom.gateway.controller;

import com.dayitw.warroom.gateway.dto.EpisodeListEnvelopeDto;
import com.dayitw.warroom.gateway.dto.ErrorResponseDto;
import com.dayitw.warroom.gateway.dto.LiveTrackingStatusDto;
import com.dayitw.warroom.gateway.dto.RefreshAcceptedDto;
import com.dayitw.warroom.gateway.dto.RefreshConflictDto;
import com.dayitw.warroom.gateway.exception.LiveRefreshConflictException;
import com.dayitw.warroom.gateway.service.EpisodeClient;
import com.fasterxml.jackson.databind.JsonNode;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Pass-through episode endpoints (feature 009). 1:1 mirrors 005 inference_service:
 * GET /api/v1/episodes -> 005 GET /api/v1/episodes
 * GET /api/v1/episodes/{id} -> 005 GET /api/v1/episodes/{id}
 *
 * Response bodies forwarded verbatim; only HTTP semantics (timeout, error
 * mapping, X-Request-Id propagation) handled here.
 */
@RestController
@RequestMapping("/api/v1/episodes")
@Tag(name = "Episodes", description = "Proxy to 005 episode artefact endpoints (feature 009)")
public class EpisodeController {

    private static final Logger log = LoggerFactory.getLogger(EpisodeController.class);
    private final EpisodeClient episodeClient;

    public EpisodeController(EpisodeClient episodeClient) {
        this.episodeClient = episodeClient;
    }

    @GetMapping
    @Operation(
            summary = "列出可用 episode（MVP：1 筆 OOS run）",
            description = "Pass-through GET /api/v1/episodes；timeout 5s。")
    @ApiResponses({
            @ApiResponse(responseCode = "200",
                    content = @Content(schema = @Schema(implementation = EpisodeListEnvelopeDto.class))),
            @ApiResponse(responseCode = "503", description = "005 不可達或 artefact 未載入",
                    content = @Content(schema = @Schema(implementation = ErrorResponseDto.class)))
    })
    public ResponseEntity<EpisodeListEnvelopeDto> list() {
        long start = System.currentTimeMillis();
        var envelope = episodeClient.listEpisodes();
        log.info("event=episode.list.completed requestId={} durationMs={}",
                MDC.get("requestId"), System.currentTimeMillis() - start);
        return ResponseEntity.ok(envelope);
    }

    @GetMapping("/{episodeId}")
    @Operation(
            summary = "取單一 episode 完整 detail",
            description = "Pass-through GET /api/v1/episodes/{id}；body 為 JsonNode 以避免 14"
                    + " 個 nested DTO 的維護負擔（仍由 005 端 strict-validate）。"
                    + " timeout 10s。")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "完整 EpisodeDetailEnvelope"),
            @ApiResponse(responseCode = "404", description = "EPISODE_NOT_FOUND",
                    content = @Content(schema = @Schema(implementation = ErrorResponseDto.class))),
            @ApiResponse(responseCode = "503", description = "005 不可達",
                    content = @Content(schema = @Schema(implementation = ErrorResponseDto.class)))
    })
    public ResponseEntity<JsonNode> detail(@PathVariable("episodeId") String episodeId) {
        long start = System.currentTimeMillis();
        var body = episodeClient.getEpisodeDetail(episodeId);
        log.info("event=episode.detail.completed requestId={} episodeId={} durationMs={}",
                MDC.get("requestId"), episodeId, System.currentTimeMillis() - start);
        return ResponseEntity.ok(body);
    }

    @GetMapping("/live/status")
    @Operation(
            summary = "取得 live tracking 當前狀態（feature 010 FR-015 / FR-027）",
            description = "Pass-through GET /api/v1/episodes/live/status；timeout 5s。"
                    + " 前端 polling 在按下 refresh 後每 3 秒抓一次。")
    @ApiResponses({
            @ApiResponse(responseCode = "200",
                    content = @Content(schema = @Schema(implementation = LiveTrackingStatusDto.class))),
            @ApiResponse(responseCode = "503", description = "005 不可達",
                    content = @Content(schema = @Schema(implementation = ErrorResponseDto.class)))
    })
    public ResponseEntity<LiveTrackingStatusDto> liveStatus() {
        long start = System.currentTimeMillis();
        var status = episodeClient.getLiveStatus();
        log.info("event=episode.live_status.completed requestId={} durationMs={}",
                MDC.get("requestId"), System.currentTimeMillis() - start);
        return ResponseEntity.ok(status);
    }

    @PostMapping("/live/refresh")
    @Operation(
            summary = "手動觸發 daily tracker pipeline（feature 010 FR-016 / SC-004）",
            description = "Pass-through POST /api/v1/episodes/live/refresh。"
                    + " 202 + estimated_duration_seconds 為快樂路徑；"
                    + " 409 表示既有 pipeline 正在跑，body verbatim 透傳"
                    + "（含 running_pid / running_started_at / poll_status_url）。")
    @ApiResponses({
            @ApiResponse(responseCode = "202",
                    content = @Content(schema = @Schema(implementation = RefreshAcceptedDto.class))),
            @ApiResponse(responseCode = "409", description = "Pipeline already running",
                    content = @Content(schema = @Schema(implementation = RefreshConflictDto.class))),
            @ApiResponse(responseCode = "503", description = "005 不可達",
                    content = @Content(schema = @Schema(implementation = ErrorResponseDto.class)))
    })
    public ResponseEntity<?> liveRefresh() {
        long start = System.currentTimeMillis();
        try {
            var accepted = episodeClient.triggerLiveRefresh();
            log.info("event=episode.live_refresh.accepted requestId={} pipelineId={} durationMs={}",
                    MDC.get("requestId"), accepted.pipelineId(),
                    System.currentTimeMillis() - start);
            return ResponseEntity.accepted().body(accepted);
        } catch (LiveRefreshConflictException ex) {
            log.info("event=episode.live_refresh.conflict requestId={} durationMs={}",
                    MDC.get("requestId"), System.currentTimeMillis() - start);
            return ResponseEntity.status(HttpStatus.CONFLICT).body(ex.payload());
        }
    }
}
