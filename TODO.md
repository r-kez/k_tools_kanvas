Este é o plano de mestre para o **Kanvas**. Ele foi estruturado para ser modular, facilitando a vida das IAs que você for utilizar para codificar. O foco é performance via GPU e organização de arquivos profissional.

---

## 📋 Kanvas: TODO List (Fase de Desenvolvimento)

### Fase 1: Infraestrutura de Desenho (The Core)
*   [ ] Implementar o `draw_handler` no Node Editor usando `POST_VIEW`.
*   [ ] Criar classe `KanvasTexture` para gerenciar o upload de `bpy.types.Image` para `gpu.types.GPUTexture`.
*   [ ] Sistema de cache: Garantir que uma imagem só seja carregada na VRAM uma única vez.
*   [ ] Shader Setup: Configurar o shader `IMAGE` do Blender para suportar transparência (Alpha Blending).

### Fase 2: Gestão de Assets (File System)
*   [ ] Lógica de detecção de caminho: Verificar se o `.blend` está salvo.
*   [ ] Sistema de cópia automática: Mover imagens externas para `//assets/kanvas-ref/`.
*   [ ] Função de Empacotamento: Opção para dar `pack()` na imagem diretamente pelo add-on.
*   [ ] Relativização de caminhos: Converter `C:\Users\...` para `//assets/...` automaticamente.

### Fase 3: Interatividade (Modal Operator)
*   [ ] Criar um operador `modal` para escutar eventos de mouse e teclado.
*   [ ] **Hitbox Detection:** Lógica matemática para saber se o mouse está sobre uma imagem.
*   [ ] Transformações básicas: Mover (G), Escalar (S) e Deletar (X).
*   [ ] Sincronização de Zoom/Pan: Garantir que a imagem não "descole" do grid ao navegar no editor.

### Fase 4: UI & Polimento
*   [ ] Painel na N-Panel (K-Tools tab).
*   [ ] Controle de opacidade individual por imagem.
*   [ ] Botão de "Show/Hide" global para limpar o visual rapidamente.
*   [ ] Suporte a múltiplos editores (Shader, Geo Nodes, Compositor).

---

## 🛠 Plano de Implementação para Agentes de IA

Ao alimentar sua IA com este plano, peça para ela focar em um módulo por vez. **Não peça o add-on inteiro de uma vez.**

### 1. Instrução para o Módulo de Desenho (GPU)
"Crie um sistema de desenho usando `gpu.types.GPUTexture` que rode no `space_data` do Node Editor. O desenho deve ocorrer no espaço `POST_VIEW` para que a imagem acompanhe o zoom e o pan dos nodes. Use um dicionário global para armazenar as texturas e evitar recarregamento desnecessário."

### 2. Instrução para o Módulo de Arquivos (IO)
"Desenvolva uma função que receba um caminho de imagem. Se a imagem estiver fora da pasta do projeto, copie-a para uma subpasta chamada `assets/kanvas-ref/` relativa ao arquivo `.blend` atual. Certifique-se de tratar erros caso o arquivo `.blend` ainda não tenha sido salvo no disco."

### 3. Instrução para o Módulo Interativo (Modal)
"Implemente um operador modal que converta a posição do mouse (coordenadas de região) para o espaço de visualização 2D do Node Editor. O operador deve permitir selecionar uma imagem (baseado em sua bounding box) e movê-la alterando suas propriedades de localização."

---

## 💡 Ideias de Diferenciais (Para o futuro)

*   **GIF Support:** Usar o Blender para extrair frames de GIFs e dar play na referência dentro do Node Editor.
*   **Node Snapping:** Opção para "grudar" uma imagem de referência em um node específico (ela se move junto com o node).
*   **Grease Pencil Integration:** Permitir desenhar anotações por cima das imagens de referência usando as ferramentas nativas do Blender.

---

## 🇰🇷 Vocabulário Coreano para o Projeto

*   **계획 (Gye-hwek)**: Significa "Plano" ou "Projeto".
    *   *Sentido Literal:* Cálculo ou deliberação para fazer algo. É o que este documento representa.
*   **준비 (Jun-bi)**: Significa "Preparação" ou "Pronto".
    *   *Sentido Literal:* Estar equipado e pronto para a ação. Use isso quando o sistema de texturas estiver carregado e **준비** para ser desenhado.
*   **그림판 (Geurim-pan)**: Significa "Tela de desenho" ou "Paleta".
    *   *Sentido Literal:* **그림** (imagem/desenho) + **판** (tabuleiro/superfície). É a essência do seu **Kanvas**.

---
**Dica para os Agentes de IA:** Como você não é programador, peça sempre para a IA comentar as seções que lidam com as matrizes de conversão de tela (`view2d`), pois essa é a parte mais complexa de debugar visualmente.