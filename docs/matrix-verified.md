# Matriz verificada ao vivo (2026-10-04)

Identificação da conta e dos recursos omitida para preservar a privacidade.

## Imagem — 15/15 completed
| Modelo | 1:1 | 9:16 | 16:9 | 3:4 | 4:3 |
|---|---|---|---|---|---|
| nano_banana_pro | ok | ok | ok | ok | ok |
| nano_banana_2 | ok | ok | ok | ok | ok |
| nano_banana_lite | ok | ok | ok | ok | ok |

Payload `ogiZ0b` byte-igual ao golden FlowKit
(`extension/tests/ogiz0b_parity.test.mjs`).

## Omni texto (YhhmEf) — 4/4 completed
| Duração | Resultado |
|---|---|
| 4s | completed |
| 6s | completed |
| 8s | completed |
| 10s | completed |
| 8s (reteste) | completed |

## Omni start (eb1hJf) — completed

## Omni start+end (nprQif) — completed

## Omni refs (MZZa6b) — 4/4 completed
| Duração | Resultado |
|---|---|
| 4s | completed |
| 6s | completed |
| 8s | completed |
| 10s | completed |
| 8s (reteste) | completed |

## Veo lite (start-only 8s 720p, verificado)
`veo_lite` aceitou submit e concluiu a geração (completed).
Schema aceita `omni` + `veo_lite`; `veo_lite_low_priority` e
`veo_fast_ultra` seguem não implementados (`rpc_rejected` code 7).

## Upscale (verificado 2026-10-05)
| Caso | Resultado |
|---|---|
| Imagem 2K com mídia gerada | completed com imagem inline |
| Imagem 4K com mídia de upload | `rpc_rejected` code 3 em `SPrCad` (conta pro, 4K exige ultra) |
| Vídeo 1080p | pending→completed via `as29s` `<media>_upsampled`; vídeo anterior com upscale baixado e verificado (1920×1080, 8s, h264) |

Upscale de vídeo devolve mídia com sufixo `_upsampled` legível via
`as29s` direto; `jwpduf` não serve para esse caso.

## Custos (fonte: código/skills FlowKit — Google não expõe via API)
| Modelo | Custo |
|---|---|
| Omni texto/frame/refs 4s | 15 créditos |
| Omni 6s | 20 créditos |
| Omni 8s | 25 créditos |
| Omni 10s | 30 créditos |
| `veo_3_1_i2v_lite` | ~5 créditos / vídeo 8s |
| `veo_3_1_i2v_lite_low_priority` | 0 créditos (qualquer tier) |
| `veo_3_1_i2v_s_fast_ultra` | ~10 créditos / vídeo |
| Imagem nano (pro/2/lite) | não documentado no código — ver UI do Flow |
| Upscale imagem/vídeo | não documentado — ver UI do Flow |

Tier: `veo_lite` roda em qualquer tier; ultra exige `TIER_TWO`;
low-priority `*_relaxed` exige `SERVICE_TIER_ULTRA` (falha silenciosa
em `ADVANCED`).

## Notas
- reCAPTCHA via `__fk_hijack.pristine` (`L3-setter`); sem pristine,
  submit é recusado antes de gastar crédito
  (`native_recaptcha_automation_unsupported`).
- Poll de `operation_id` exige lookup no listing `Zzl0ze` mesmo após
  `CAE` — sem isso, jobs com ref/start parecem presos em `pending`.
