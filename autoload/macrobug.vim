" Some code inspired from vim-multiple-cursors
" https://github.com/terryma/vim-multiple-cursors/blob/47c9e3fb11a202a9a2fa1d591ec990a41e4221c4/autoload/multiple_cursors.vim#L811
" Thanks a lot to this guy and all of the contributors for
" this amazing script!

if !has('python') && !has('python3')
  echo 'MacroBug needs python support. See :help nvim-python'
  finish
endif

let s:hi_cursor = 'macro_bug_cursor'
let s:hi_visual = 'macro_bug_visual'
let s:cursor_priority = 99999
let s:visual_priority = 99998
if !hlexists(s:hi_cursor)
  exe 'hi '.s:hi_cursor.' term=reverse cterm=reverse gui=reverse'
endif
if !hlexists(s:hi_visual)
  exe 'hi link '.s:hi_visual.' Visual'
endif

function! s:apply_state(change_root, cursor_root)
  execute "silent undo " . a:change_root
  call cursor(a:cursor_root[0], a:cursor_root[1])
endfunction

function! macrobug#execute_macro_chunk(arguments)
  execute a:arguments.target_winnr . "wincmd w"
  setlocal modifiable

  call s:apply_state(a:arguments.change_root, a:arguments.cursor_root)

  try
    execute "normal " . a:arguments.keys
    call macrobug#draw_cursor_and_visual()
  catch
  finally
    setlocal nomodifiable
    let undotree_seq_cur = undotree()['seq_cur']
    let cursor_pos = getpos('.')
    execute a:arguments.winnr . "wincmd w"
  endtry
  return { 'undotree_seq_cur': undotree_seq_cur, 'cursor_pos': cursor_pos[1:2] }
endfunction

function! macrobug#map_keys()
  if !exists('g:macrobug_step_forward')
    let g:macrobug_step_forward = '>'
  endif
  if !exists('g:macrobug_step_backward')
    let g:macrobug_step_backward = '<'
  endif
  exe 'nnoremap <silent><buffer> '.g:macrobug_step_backward.
    \ ' :MacroStepBackward<cr>'
  exe 'nnoremap <silent><buffer> '.g:macrobug_step_forward.
    \ ' :MacroStepForward<cr>'
endfunction


function! macrobug#apply_state(target_winnr, change_root, cursor_root)
  let orig_win = winnr()
  execute a:target_winnr . "wincmd w"
  call s:apply_state(a:change_root, a:cursor_root)
  call macrobug#draw_cursor_and_visual()
  execute orig_win . "wincmd w"
endfunction


function! macrobug#draw_cursor_and_visual()
  call macrobug#unset_cursor_and_visual()
  let pos = getpos('.')
  let s:cursor_id = matchadd(s:hi_cursor, '\%'.pos[1].'l\%'.pos[2].'c', s:cursor_priority)
  let cur_mode = mode()
  if cur_mode ==# 'V' || cur_mode ==# 'v' || cur_mode ==# "\<c-v>"
    call s:quit_visual()
    call s:draw_visual(cur_mode)
  endif
endfunction

function! macrobug#unset_cursor_and_visual()
  if exists('s:cursor_id')
    call matchdelete(s:cursor_id)
    unlet s:cursor_id
  endif
  if exists('s:visual_ids')
    for id in s:visual_ids
      call matchdelete(id)
    endfor
    unlet s:visual_ids
  endif
endfunction


function! s:quit_visual()
  exe "normal! \<Esc>"
endfunction

function! s:draw_visual(mode)
  let vposbegin = getpos("'<")[1:2]
  let vposend = getpos("'>")[1:2]
  let linebegin = vposbegin[0]
  let lineend = vposend[0]
  let colbegin = min([vposbegin[1], vposend[1]])
  let colend = max([vposbegin[1], vposend[1]])
  if a:mode ==# 'V'
    let pattern = printf('\%%>%il\%%<%il',
          \ (linebegin - 1),
          \ (lineend + 1))
    let s:visual_ids = [matchadd(s:hi_visual, pattern, s:visual_priority)]
  elseif a:mode ==# "\<c-v>" || (a:mode ==# 'v' && linebegin ==# lineend)
    let pattern = printf('\%%>%il\%%<%il\%%>%ic\%%<%ic',
          \ (linebegin - 1),
          \ (lineend + 1),
          \ (colbegin - 1),
          \ (colend + 1))
    let s:visual_ids = [matchadd(s:hi_visual, pattern, s:visual_priority)]
  elseif a:mode ==# 'v'
    let pattern = printf('\%%>%il\%%<%il', linebegin, lineend)
    let s:visual_ids = [matchadd(s:hi_visual, pattern, s:visual_priority)]
    let first_line_pattern = printf('\%%>%il\%%<%il\%%>%ic',
          \ (linebegin - 1),
          \ (linebegin + 1),
          \ (vposbegin[1] - 1))
    let s:visual_ids = add(s:visual_ids, matchadd(s:hi_visual, first_line_pattern, s:visual_priority))
    let last_line_pattern = printf('\%%>%il\%%<%il\%%<%ic',
          \ (lineend - 1),
          \ (lineend + 1),
          \ (vposend[1] + 1))
    let s:visual_ids = add(s:visual_ids, matchadd(s:hi_visual, last_line_pattern, s:visual_priority))
  endif
endfunction
