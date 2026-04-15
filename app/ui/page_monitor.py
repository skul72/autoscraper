from __future__ import annotations


def render_page_monitor() -> str:
    return """<!DOCTYPE html>
<html lang='pt-BR'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>UltraPackV2 · Monitor: Plugins</title>
<link rel='stylesheet' href='/assets/styles.css'>
</head>
<body>
<div class='wrap'>
  <h1>UltraPackV2 · Monitor: Plugins</h1>
  <div class='card'>
    <div class='section-title'>Slots</div>
    <div class='form-grid'>
      <div class='field'><label for='slot_select'>Carregar slot existente</label><div class='row'><select id='slot_select'></select><button class='btn-info' onclick='switchSlot()'>Carregar</button><button class='btn-top' id='slot_delete_btn' onclick='deleteCurrentSlot()'>🗑</button></div></div>
      <div class='field'><label for='new_slot_name'>Criar novo slot</label><div class='row'><input id='new_slot_name' type='text'><button class='btn-info' onclick='createSlot()'>Criar</button></div></div>
      <div class='field'><label for='slot_default_checkbox'>Slot default</label><div class='row'><label class='checkbox-item' style='max-width:240px;'><input id='slot_default_checkbox' type='checkbox' onchange='setDefaultSlotToggle()'><span class='checkbox-text'><span>Definir slot atual como default</span><span class='checkbox-meta'>Ao ativar aqui, os outros deixam de ser default.</span></span></label></div></div>
      <div class='field'><label>Resumo do slot</label><div class='small'>Slot atual: <strong id='slot_current_label'>-</strong><br>Slot default: <strong id='slot_default_label'>-</strong></div></div>
    </div>
  </div>
  <div class='card'>
    <div class='section-title'>Configuração</div>
    <div class='form-grid'>
      <div class='field'><label for='verify_mode'>Validação</label><select id='verify_mode'><option value='normal'>Normal</option><option value='complete'>Completo</option></select></div>
      <div class='field'><label for='scope_mode'>Escopo</label><select id='scope_mode' onchange='toggleScopeFields()'><option value='all'>Todas as categorias</option><option value='range'>Intervalo por índice</option><option value='match'>Filtrar por nome/URL</option><option value='selected'>Selecionar no checklist</option></select></div>
      <div class='field' id='field_range_start'><label for='scope_start'>Índice inicial</label><input id='scope_start' type='number' min='1' value='1'></div>
      <div class='field' id='field_range_end'><label for='scope_end'>Índice final</label><input id='scope_end' type='number' min='0' value='0'></div>
      <div class='field'><label for='save_every_items'>Salvar a cada X itens</label><input id='save_every_items' type='number' min='1' value='5'></div>
      <div class='field'><label for='save_every_minutes'>Salvar a cada X minutos</label><input id='save_every_minutes' type='number' min='1' value='1'></div>
      <div class='field' id='field_match' style='grid-column:1 / -1'><label for='scope_match_text'>Filtro por nome/URL</label><textarea id='scope_match_text'></textarea></div>
      <div class='field' id='field_selected_categories' style='grid-column:1 / -1; display:none;'><label>Categorias encontradas <span class='badge' id='available_categories_count'>0</span> <span class='badge' id='selected_categories_count'>0 selecionadas</span></label><div id='selected_categories_list' class='checkbox-list'></div></div>
    </div>
    <div class='row' style='margin-top:14px'><button class='btn-info' onclick='saveConfig()'>✅ Confirmar</button></div>
  </div>
  <div class='card'><div class='section-title'>Ações</div><div class='row' style='margin-bottom:10px'><button id='primary_run_button' class='btn-top' onclick='runPrimary()'>▶️ Iniciar</button><button class='btn-top' onclick="postAction('/pause')">⏸️ Pausar</button><button class='btn-top' onclick="postAction('/resume')">▶️ Continuar</button><button class='btn-top' onclick="postAction('/stop')">⏹️ Parar</button><button class='btn-top' onclick="postAction('/rebuild')">🧩 Reconstruir</button><button class='btn-top' onclick="postAction('/clear_slot_data')">🧹 Zerar</button></div><div class='quick-grid'><button class='btn-action' onclick="postAction('/refresh_categories')">🔄 Atualizar categorias</button><button class='btn-action' onclick="runMode('links_only')">🔎 Detectar novos links</button><button class='btn-action' onclick="runMode('existing_review')">♻️ Revisar versões</button><button class='btn-action' onclick="runMode('selected_sync')">🗂️ Sincronizar selecionadas</button></div></div>
  <div class='card'><div class='section-title'>Status</div><div class='grid'>
      <div class='label'>Estado:</div><div id='status'>-</div><div class='label'>Fluxo atual:</div><div id='run_mode_label'>-</div><div class='label'>Fase atual:</div><div id='current_phase'>-</div><div class='label'>Tempo:</div><div id='timer_text'>0:00:00</div><div class='label'>Resumo:</div><div id='summary'>-</div>
      <div class='label'>Validação atual:</div><div id='verify_mode_view'>-</div><div class='label'>Escopo atual:</div><div id='scope_mode_view'>-</div><div class='label'>Salvar a cada X itens:</div><div id='save_every_items_status'>0</div><div class='label'>Salvar a cada X minutos:</div><div id='save_every_minutes_status'>0</div>
      <div class='label'>Categoria atual:</div><div id='current_category'>-</div><div class='label'>Item atual:</div><div id='current_item'>-</div><div class='label'>Itens salvos:</div><div id='saved_count'>0</div><div class='label'>Itens pendentes:</div><div id='pending_count'>0</div>
      <div class='label'>Itens em fila:</div><div id='queue_detected_count'>0</div><div class='label'>Novos links detectados:</div><div id='new_links_detected'>0</div><div class='label'>Links existentes detectados:</div><div id='existing_links_detected'>0</div><div class='label'>Novos itens adicionados:</div><div id='new_items_added'>0</div>
      <div class='label'>Itens atualizados:</div><div id='items_updated'>0</div><div class='label'>Itens sem mudança:</div><div id='items_unchanged'>0</div><div class='label'>Categorias reutilizadas:</div><div id='reused_categories'>0</div><div class='label'>Categorias refeitas:</div><div id='refetched_categories'>0</div><div class='label'>Fila de continuação:</div><div id='resume_info'>-</div><div class='label'>Última atualização:</div><div id='updated_at'>-</div>
  </div></div>
  <div class='card'><div class='section-title'>Log</div><pre id='logs'></pre><div class='row' style='margin-top:14px'><button class='btn-info' onclick='copyFullLog()'>📋 Copiar log inteiro</button></div></div>
</div>
<script src='/assets/app.js'></script>
</body>
</html>"""
