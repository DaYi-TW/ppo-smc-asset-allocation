package com.dayitw.warroom.gateway.controller;

import com.dayitw.warroom.gateway.dto.EpisodeListEnvelopeDto;
import com.dayitw.warroom.gateway.dto.ErrorResponseDto;
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
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
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
}
