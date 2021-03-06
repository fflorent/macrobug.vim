''' MacroBug python Module, managing commands and events.'''

import neovim

class State(object):
    ''' Represents a state for cursor root positions and change root '''
    def __init__(self, change_root, cursor_root):
        self.change_root = change_root
        self.cursor_root = cursor_root

class StateStack(object):
    ''' Stack for undo sequence and cursor position states '''

    def __init__(self, state):
        self._list = [state]

    def push(self, state):
        ''' Add a new state after the current index '''
        self._list.append(state)

    def pop(self):
        ''' Remove and return last state '''
        if len(self._list) > 1:
            self._list.pop()

    @property
    def current(self):
        ''' Return current state (i.e. the last in the stack '''
        return self._list[-1]

class MacroBug(object):
    ''' Instance of the Debugger '''
    def __init__(self, vim, register_key):
        self.vim = vim
        if len(register_key) != 1:
            # doesn't seem to work. What do I do wrong here?
            raise MacroBugException('Expecting a register as parameter.' +
                                    ' See :help register')
        self.register_key = register_key
        self.target_win = self.vim.current.window

        state = State(self._get_change_root(), self.target_win.cursor[:])
        self.states = StateStack(state)

        self.vim.call('macrobug#draw_cursor_and_visual')

        self.vim.command('setlocal nomodifiable')
        # normal! ignores the mapping the user has set up
        # The V before the pasting is used to avoid the creation of a new line
        #  (is there any better solution?
        #   self.vim.eval doesn't seem to work currently)
        self.vim.command('new +normal!\\ V"%cp0' % register_key)
        self.buffer = self.vim.current.buffer
        if len(self.buffer) > 1:
            raise MacroBugException('Unexpected carriage return in macro')
        self.window = self.vim.current.window
        self.window.height = 2
        self.last_col = self.current_col
        self.vim.command('setlocal noswapfile', async=True)
        # Cannot register to keypress event yet, do some workaround here.
        self.vim.command(('autocmd CursorMoved,CursorMovedI <buffer=%d> ' +
                          ':call rpcnotify(%d, "macrobug:cursormove")') %
                         (self.buffer.number, self.vim.channel_id),
                         async=True)
        self.vim.command(('autocmd BufUnload <buffer=%d> ' +
                          ':call rpcnotify(%d, "macrobug:quit")') %
                         (self.buffer.number, self.vim.channel_id),
                         async=True)
        self.vim.command('inoremap <silent><buffer> <cr> <lt>cr>', async=True)

        self.vim.call('macrobug#map_keys')

    def _escape_keys(self, keys):
        return self.vim.replace_termcodes(keys).replace('"', '\\"')

    def _get_change_root(self):
        change_root = self.vim.eval('undotree()["seq_cur"]')
        if change_root is None:
            raise MacroBugException('Cannot find current sequence of the undotree')
        return change_root

    @property
    def change_root(self):
        ''' Get the undo sequence from which we start running the macro '''
        return self.states.current.change_root

    @property
    def cursor_root(self):
        ''' Get the cursor position from which we start running the macro '''
        return self.states.current.cursor_root

    @property
    def current_col(self):
        ''' Get the current column position in the debugger window '''
        return self.window.cursor[1]

    @property
    def macro(self):
        ''' The content of the macro (should be in a single line '''
        return self.buffer[0]

    @property
    def winnr(self):
        ''' The debugger window number '''
        return self.vim.eval('bufwinnr(%i)' % self.window.buffer.number)

    @property
    def target_winnr(self):
        ''' The target (debuggee) window number '''
        return self.vim.eval('bufwinnr(%i)' % self.target_win.buffer.number)

    def save_register(self):
        ''' Handle MacroSave '''
        if not self.window.valid:
            raise MacroBugException('Cannot access debugger window')
        self.vim.command('let @%c="%s"' % (self.register_key, self.macro.replace('"', '\\"')))

    def quit(self):
        ''' Handle MacroQuit '''
        if not self.window or not self.window.valid:
            return
        self.vim.command('%iwindo q!' % self.winnr)

    def check_cursor_moved(self):
        ''' Check whether the cursor moved or not (in normal or insert mode) '''
        if self.current_col == self.last_col:
            return False
        self.last_col = self.current_col
        return True

    def run_macro_chunk(self):
        ''' Run the Macro until the position of the cursor. '''
        # Get the keys from the beginning to the cursor
        keys_to = self.current_col + 1
        self.run_macro_to_pos(keys_to)

    def run_macro_to_pos(self, keys_to):
        ''' Run the macro to character position (keys_to) '''
        escaped_keys = self._escape_keys(self.macro[0:keys_to])
        self.target_win.cursor = self.cursor_root[:]
        self.vim.command('echom "%s"' % self.change_root)

        return self.vim.eval(('''macrobug#execute_macro_chunk({
                'target_winnr': %d,
                'winnr': %d,
                'change_root': %d,
                'cursor_root': %s,
                'keys': "%s"
            })''' % (self.target_winnr, self.winnr, self.change_root,
                     self.cursor_root, escaped_keys)).replace('\n', ' '))

    def step_forward(self):
        ''' Run the macro once to step forward '''
        res = self.run_macro_to_pos(len(self.macro))

        self.states.push(State(res['undotree_seq_cur'], res['cursor_pos']))

    def step_backward(self):
        ''' Undo last macro execution to step backward '''
        self.states.pop()
        self.vim.eval(('macrobug#apply_state(%d, %d, %s)')
                      % (self.target_winnr, self.change_root, self.cursor_root))

    def on_quit(self):
        ''' Handle when the debugger window has just been closed. '''
        if self.window and self.window.valid:
            return
        if not self.target_win or not self.target_win.valid:
            return
        focused_win = self.vim.current.window
        self.vim.current.window = self.target_win
        self.vim.command('setlocal modifiable')
        self.vim.command('undo %i' % self.change_root)
        self.vim.command('call macrobug#unset_cursor_and_visual()')
        self.vim.current.window = focused_win
        self.states = None

class MacroBugException(Exception):
    ''' MacroBug exception '''
    pass

@neovim.plugin
class Plugin(object):
    ''' Main module (handling events and managing MacroBug instances) '''
    def __init__(self, vim):
        self.vim = vim
        self.instance = None

    @neovim.command('MacroBug', nargs='1')
    def start_macro_bug(self, args):
        ''' Handle :MacroBug command '''
        if self.instance:
            self._echo_error('MacroBug debugger instance already open!')
            return

        try:
            self.instance = MacroBug(self.vim, args[0])
        except MacroBugException as exc:
            self._echo_error(exc)
            if not self.instance:
                return
            elif self.instance.window and self.instance.window.valid:
                self.quit()
            else:
                self.on_quit()

    def _echo_error(self, err):
        ''' Display an error '''
        if err is Exception:
            err = err.message
        # TODO Wait, why am I not able to use echoerr???
        self.vim.command('echom "MacroBug Error: %s"' % err, async=True)

    @neovim.command('MacroSave')
    def save_register(self):
        ''' Handle :MacroSave '''
        try:
            self.instance.save_register()
        except MacroBugException as exc:
            self._echo_error(exc)

    @neovim.command('MacroQuit')
    def quit(self):
        ''' Handle :MacroQuit '''
        if not self.instance:
            self._echo_error('MacroBug is not open')
            return
        self.instance.quit()

    @neovim.command('MacroStepForward')
    def step_forward(self):
        ''' Handle :MacroStepForward '''
        if not self.instance:
            self._echo_error('MacroBug is not open')
            return
        self.instance.step_forward()

    @neovim.command('MacroStepBackward')
    def step_backward(self):
        ''' Handle :MacroStepBackward '''
        if not self.instance:
            self._echo_error('MacroBug is not open')
            return
        self.instance.step_backward()

    @neovim.rpc_export('macrobug:quit')
    def on_quit(self):
        ''' Handle when the debugger window has just been closed. '''
        self.instance.on_quit()
        self.instance = None

    @neovim.rpc_export('macrobug:cursormove')
    def on_cursor_move(self):
        ''' Handle when the cursor moved '''
        if not self.instance.check_cursor_moved():
            return
        self.instance.run_macro_chunk()
