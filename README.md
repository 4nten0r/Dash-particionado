 Guia de Execução — Substituto (Férias do Ícaro)

Este é o guia prático passo a passo para executar o pipeline de dados da Natura e atualizar as bases do Dashboard.

---

## ⚠️ 1. Pré-requisitos (O que você vai precisar)

Antes de começar as execuções diárias, certifique-se de que você possui:
- [ ] **Python instalado** no seu computador.
- [ ] **Pasta `BASE`** copiada para a sua **Área de Trabalho**.
- [ ] **Arquivo `.env`** salvo dentro da pasta `BASE`.

---

## 📥 2. Recebendo as bases da Natura

Salve os dois arquivos recebidos diretamente na pasta **Documentos** do seu computador. **Atenção: Não renomeie os arquivos!**
*   **Arquivo de Danos:** Começa com `Base_R`
*   **Arquivo de Faltas:** Começa com `PPM Falta`

---

## ▶️ 3. Como executar o script (Passo a Passo)

1. Abra a pasta `BASE` que está na sua Área de Trabalho.
2. Segure a tecla **`Shift`**, clique com o **botão direito** do mouse em qualquer espaço vazio dentro da pasta e selecione **"Abrir janela do PowerShell aqui"** (ou "Abrir no Terminal").
3. No terminal que se abrir, digite o seguinte comando e aperte `Enter`:
   ```bash
   venv\Scripts\python main.py
   ```
4. O sistema fará **3 perguntas**. Responda da seguinte forma:
   *   **Browser invisível?** → Digite `s` e dê `Enter`.
   *   **Data inicial dos ofensores** → Digite a data desejada (exemplo: `01/04/2026`) e dê `Enter`.
   *   **Data final** → Apenas aperte `Enter` (o sistema usará a data de hoje automaticamente).

⏳ **Aguarde cerca de 5 minutos** até aparecer a mensagem de sucesso: `✅ Pipeline concluído!`

---

## 📤 4. Finalização e Atualização do Dashboard

1. Navegue até a pasta de resultados: `BASE\outputs\DATA-DE-HOJE\`.
2. Copie o arquivo gerado chamado **`tratativas.xlsx`**.
3. **Envie esse arquivo** para o Ícaro (via WhatsApp ou E-mail).
   * *Nota: O Ícaro fará o upload no OneDrive pelo celular para que o dashboard seja atualizado automaticamente.*

---

## 🆘 5. Resolução de Problemas

Se o processo parar ou apresentar alguma falha:
- Tire um **print (captura de tela)** do terminal mostrando o erro.
- Envie a imagem para o Ícaro analisar.
