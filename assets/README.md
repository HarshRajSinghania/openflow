# Identidade visual e demonstração

## Arte de origem

`flow-showcase/portal.jpg` é uma imagem gerada por IA pelo próprio OpenFlow, via API REST e navegador Chromium gerenciado, sem extensão. Não é fotografia, vídeo ou captura de interface.

- Modelo: Nano Banana 2.1 (`nano_banana_2`).
- Proporção: `16:9`; saída: 1376 × 768, JPEG.
- Data: 2026-10-17.
- Uma geração, seguida de download com assinatura de arquivo verificada e inspeção visual.

Prompt completo:

> Cinematic architectural visualization, a monumental circular portal made of brushed titanium and dark basalt opening onto a serene alien coastal landscape, luminous turquoise water, sculptural black rock formations, distant warm amber sun, atmospheric mist, subtle reflections on wet charcoal stone floor, refined contemporary art direction, premium science fiction film still, restrained teal and warm amber palette, realistic materials, dramatic wide composition, main circular portal slightly right of center, no people, no animals, no text, no letters, no logos, no watermark.

## Composição da capa

`banner.png` combina tipografia, formas vetoriais rasterizadas e dois recortes da mesma imagem. Os painéis não representam dois resultados distintos ou um vídeo. O pequeno bloco de código é ilustrativo, não uma captura da API.

A composição é local e não consome créditos. Requer Python com Pillow e fontes DejaVu Sans regular/negrito. Esses recursos são ferramentas de design, não dependências de execução do OpenFlow.

```bash
# Em um ambiente de design com Pillow instalado:
python3 -I scripts/build_banner.py

# Para outra instalação de fontes:
python3 -I scripts/build_banner.py --font-dir /caminho/das/fontes/dejavu
```

O diretório de fontes precisa conter `DejaVuSans.ttf` e `DejaVuSans-Bold.ttf`. Use `--source` e `--output` para compor variantes. O script substitui o arquivo de saída; salve variantes com outro nome se quiser preservar a anterior. Nenhuma fonte binária é distribuída neste repositório.

A arte gerada é apresentada como demonstração do produto. A licença MIT do código não concede direitos sobre serviços de terceiros; consulte também os termos aplicáveis ao conteúdo gerado.

`banner-social.png` é uma peça histórica, não utilizada pelo README atual.
