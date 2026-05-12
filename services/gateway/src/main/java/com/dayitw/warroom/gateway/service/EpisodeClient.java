package com.dayitw.warroom.gateway.service;

import com.dayitw.warroom.gateway.dto.EpisodeListEnvelopeDto;
import com.dayitw.warroom.gateway.dto.LiveTrackingStatusDto;
import com.dayitw.warroom.gateway.dto.RefreshAcceptedDto;
import com.dayitw.warroom.gateway.exception.InferenceServiceException;
import com.dayitw.warroom.gateway.exception.InferenceTimeoutException;
import com.dayitw.warroom.gateway.exception.LiveRefreshConflictException;
import com.dayitw.warroom.gateway.exception.PredictionNotReadyException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import java.time.Duration;

/**
 * Pass-through client for 005 episode endpoints (feature 009).
 *
 * <p>list / detail bodies are forwarded as raw JsonNode to avoid maintaining 14
 * deeply nested DTOs whose only purpose would be to be re-serialised verbatim.
 * The list endpoint still uses a typed envelope so swagger and tests have
 * structure to assert on.</p>
 */
@Service
public class EpisodeClient {

    private final RestClient restClient;
    private final Duration listTimeout;
    private final Duration detailTimeout;
    private final ObjectMapper objectMapper;

    public EpisodeClient(RestClient inferenceRestClient,
                         ObjectMapper objectMapper,
                         @Value("${inference.timeout.episodes-list:5s}") Duration listTimeout,
                         @Value("${inference.timeout.episodes-detail:10s}") Duration detailTimeout) {
        this.restClient = inferenceRestClient;
        this.objectMapper = objectMapper;
        this.listTimeout = listTimeout;
        this.detailTimeout = detailTimeout;
    }

    public EpisodeListEnvelopeDto listEpisodes() {
        return doCall(() -> restClient.get().uri("/api/v1/episodes")
                .retrieve()
                .body(EpisodeListEnvelopeDto.class), listTimeout);
    }

    public JsonNode getEpisodeDetail(String episodeId) {
        return doCall(() -> restClient.get().uri("/api/v1/episodes/{id}", episodeId)
                .retrieve()
                .body(JsonNode.class), detailTimeout);
    }

    /**
     * Feature 010 FR-015 / FR-027: GET /api/v1/episodes/live/status pass-through。
     */
    public LiveTrackingStatusDto getLiveStatus() {
        return doCall(() -> restClient.get().uri("/api/v1/episodes/live/status")
                .retrieve()
                .body(LiveTrackingStatusDto.class), listTimeout);
    }

    /**
     * Feature 010 FR-016 / SC-004: POST /api/v1/episodes/live/refresh pass-through。
     *
     * <p>409 處理特例：spec FR-016 要求 body verbatim 透傳 — 不能走 retrieve() 的
     * 4xx auto-throw（會被 GlobalExceptionHandler 重映射成 ErrorResponseDto，
     * 失去 running_pid / running_started_at 欄位）。改用 exchange() 攔住
     * 4xx 並直接拋 LiveRefreshConflictException，讓 controller 重新組合
     * 409 + 原始 body。</p>
     */
    public RefreshAcceptedDto triggerLiveRefresh() {
        try {
            return restClient.post().uri("/api/v1/episodes/live/refresh")
                    .exchange((req, resp) -> {
                        HttpStatus status = HttpStatus.resolve(resp.getStatusCode().value());
                        byte[] body = resp.getBody().readAllBytes();
                        if (status == HttpStatus.ACCEPTED) {
                            return objectMapper.readValue(body, RefreshAcceptedDto.class);
                        }
                        if (status == HttpStatus.CONFLICT) {
                            JsonNode payload = objectMapper.readTree(body);
                            throw new LiveRefreshConflictException(payload);
                        }
                        if (status != null && status.is5xxServerError()) {
                            throw new InferenceServiceException(
                                    "upstream 5xx: " + status, null);
                        }
                        throw new InferenceServiceException(
                                "unexpected upstream status: " + resp.getStatusCode(), null);
                    });
        } catch (LiveRefreshConflictException ex) {
            throw ex;
        } catch (ResourceAccessException ex) {
            if (ex.getCause() instanceof java.net.SocketTimeoutException) {
                throw new InferenceTimeoutException("upstream timeout", ex);
            }
            throw new InferenceServiceException("upstream connection error", ex);
        } catch (RestClientException ex) {
            throw new InferenceServiceException("upstream call failed", ex);
        }
    }

    @SuppressWarnings("unused")
    private <T> T doCall(java.util.function.Supplier<T> action, Duration timeout) {
        try {
            return action.get();
        } catch (HttpClientErrorException.NotFound ex) {
            throw new PredictionNotReadyException("episode not found");
        } catch (HttpClientErrorException ex) {
            throw new InferenceServiceException("upstream 4xx: " + ex.getStatusCode(), ex);
        } catch (HttpServerErrorException ex) {
            throw new InferenceServiceException("upstream 5xx: " + ex.getStatusCode(), ex);
        } catch (ResourceAccessException ex) {
            if (ex.getCause() instanceof java.net.SocketTimeoutException) {
                throw new InferenceTimeoutException("upstream timeout", ex);
            }
            throw new InferenceServiceException("upstream connection error", ex);
        } catch (RestClientException ex) {
            throw new InferenceServiceException("upstream call failed", ex);
        }
    }
}
