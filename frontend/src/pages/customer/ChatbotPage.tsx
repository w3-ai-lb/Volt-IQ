import { useCallback, useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Sparkles, Plus, MessageSquare, Trash2, Bot, User } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { chatService } from '@/services/api';
import { useToast } from '@/context/ToastContext';
import { getLanguage, slideFrom, t } from '@/i18n/t';

/**
 * The assistant page.
 *
 * WHAT WAS WRONG HERE
 * -------------------
 * The conversation list down the side was a hardcoded array copied out of
 * mockData, so every customer saw the same five invented threads, none of them
 * theirs. Clicking one did nothing, the bin icon did nothing, "New chat" did
 * nothing, and a microphone button offered voice input that no code anywhere
 * implemented. `sendMessage` had no catch, so one failed request left the
 * typing dots bouncing for ever.
 *
 * All four buttons now do what they say, the history is the customer's own,
 * and a failed request says so.
 */

interface Message { id: string; role: 'user' | 'bot'; text: string }
interface Conversation { id: string; title: string; date: string }

/**
 * The chips offered before the first message.
 *
 * Four of these used to be here and two of them were questions the assistant
 * has to refuse: there is no off-peak tariff on this network, and nothing in
 * the provider's data describes a solar panel. Both refusals are honest and
 * both are worth showing, but leading with two of them made a capable
 * assistant look like it knew nothing.
 *
 * These six open with what it can do, the bill, the arithmetic behind it, the
 * rate, the supply hours, and keep the two limits at the end, where they read
 * as candour rather than as the whole repertoire.
 *
 * WHAT A CHIP SENDS IS WHAT IT SAYS
 * ---------------------------------
 * It used to draw `t(s)` and send `s`. An Arabic customer pressed a chip
 * written in Arabic and watched an English sentence appear in the
 * conversation as though they had typed it, followed by an English answer.
 * The assistant's whole claim is that it answers in the language it was asked
 * in, and the first thing on the page was breaking it.
 *
 * A chip now sends the words on it — but only in the two languages the
 * assistant actually reads. Its keyword tables are English and Arabic; a
 * Spanish or Japanese sentence matches nothing and falls to the catch-all, so
 * in those five the chip keeps sending the English source and gets a real
 * answer, which is also what typing in those languages does today.
 */
const suggested = [
  'Why is my bill higher this month?',
  'How was my bill calculated?',
  'What is the price per kWh?',
  'How many hours a day is my zone supplied?',
  'What are the off-peak hours?',
  'How much can I save with solar?',
];

// The languages the assistant's own keyword tables are written in. See the
// note above `suggested`.
const UNDERSTOOD = new Set(['en', 'ar']);

/** What a chip actually sends: the words on it where that can be understood. */
const asked = (english: string) =>
  UNDERSTOOD.has(getLanguage()) ? t(english) : english;

// A function rather than a constant, because a constant is evaluated once when
// the module loads, and it was evaluated in English. An Arabic customer opened
// the page and the first thing on it was a sentence in English.
const greeting = (): Message => ({
  id: 'init',
  role: 'bot',
  text: t("Hi! I'm VoltIQ, your AI energy assistant. Ask me about your bills, usage, or ways to save energy."),
});

export default function ChatbotPage() {
  const toast = useToast();
  const [messages, setMessages] = useState<Message[]>(() => [greeting()]);
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [mobileHistoryOpen, setMobileHistoryOpen] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  // Whether the last request to the assistant succeeded. The header used to
  // say "Online" unconditionally, including when the backend was unreachable.
  const [reachable, setReachable] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  const loadHistory = useCallback(async () => {
    try {
      setConversations(await chatService.getHistory());
    } catch {
      setConversations([]);
    }
  }, []);

  useEffect(() => { loadHistory(); }, [loadHistory]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, typing]);

  const send = async (text: string) => {
    if (!text.trim() || typing) return;
    const userMsg: Message = { id: crypto.randomUUID(), role: 'user', text };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setTyping(true);
    try {
      // Passing the active conversation keeps the exchange in one thread
      // instead of starting a new one on every message.
      const numericId = activeId ? Number(activeId.replace(/^c-/, '')) : undefined;
      const res = await chatService.sendMessage(text, Number.isFinite(numericId) ? numericId : undefined);
      setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'bot', text: res.reply }]);
      setReachable(true);
      if (res.conversationId) {
        setActiveId(`c-${res.conversationId}`);
        loadHistory();
      }
    } catch {
      setReachable(false);
      // The message the customer typed stays on screen; what follows is an
      // honest failure rather than an answer that never arrived.
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: 'bot', text: t('I could not reach the assistant just now. Please try again in a moment.') },
      ]);
    } finally {
      // In `finally`, so a failure can never leave the typing dots running.
      setTyping(false);
    }
  };

  const openConversation = async (id: string) => {
    setMobileHistoryOpen(false);
    try {
      const conversation = await chatService.getConversation(id);
      setActiveId(conversation.id);
      setMessages(
        conversation.messages.length
          ? conversation.messages.map((m) => ({
              id: m.id,
              role: m.role === 'user' ? 'user' : 'bot',
              text: m.content,
            }))
          : [greeting()],
      );
    } catch {
      toast({ type: 'error', title: t('Could not open the conversation'), message: t('Please try again.') });
    }
  };

  const startNewChat = () => {
    setActiveId(null);
    setMessages([greeting()]);
    setInput('');
    setMobileHistoryOpen(false);
  };

  const removeConversation = async (id: string) => {
    try {
      await chatService.deleteConversation(id);
      setConversations((current) => current.filter((c) => c.id !== id));
      if (activeId === id) startNewChat();
      toast({ type: 'success', title: t('Conversation deleted') });
    } catch {
      toast({ type: 'error', title: t('Could not delete the conversation'), message: t('Please try again.') });
    }
  };

  const historyList = (onPick: (id: string) => void) => (
    conversations.length === 0 ? (
      <p className="px-3 py-4 text-xs text-slate-400">{t('Your past conversations will appear here.')}</p>
    ) : (
      conversations.map((c) => (
        <div
          key={c.id}
          className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm transition group ${
            activeId === c.id
              ? 'bg-primary-50 dark:bg-primary-500/10 text-primary-700 dark:text-primary-300'
              : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
          }`}
        >
          <button onClick={() => onPick(c.id)} className="flex items-center gap-2.5 flex-1 min-w-0 text-start">
            <MessageSquare className="w-4 h-4 text-slate-400 shrink-0" />
            {/* Titles come from the customer's own questions, so they are data
                and are shown as they were asked, not translated. <bdi> keeps a
                title in its own direction, so an English question in the
                right-to-left list still ends with its question mark. */}
            <span className="flex-1 truncate"><bdi>{c.title}</bdi></span>
          </button>
          <button
            onClick={() => removeConversation(c.id)}
            aria-label={t('Delete {name}').replace('{name}', c.title)}
            className="shrink-0 text-slate-300 opacity-0 group-hover:opacity-100 focus:opacity-100 hover:text-error-500 transition"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      ))
    )
  );

  return (
    <div className="h-[calc(100vh-8rem)] flex gap-4">
      {/* Sidebar history */}
      <Card className="hidden lg:flex w-72 shrink-0 flex-col p-4">
        <Button fullWidth leftIcon={<Plus className="w-4 h-4" />} className="mb-4" onClick={startNewChat}>{t('New chat')}</Button>
        <div className="flex-1 overflow-y-auto scrollbar-thin space-y-1">
          {historyList(openConversation)}
        </div>
      </Card>

      {/* Chat area */}
      <Card className="flex-1 flex flex-col p-0 overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-primary flex items-center justify-center"><Sparkles className="w-5 h-5 text-white" /></div>
            <div>
              <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t('VoltIQ Assistant')}</p>
              {/* Reflects the last request rather than asserting Online always. */}
              <p className={`text-xs flex items-center gap-1 ${reachable ? 'text-emerald-600' : 'text-error-600'}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${reachable ? 'bg-emerald-500' : 'bg-error-500'}`} />
                {reachable ? t('Online') : t('Unreachable')}
              </p>
            </div>
          </div>
          <Button variant="ghost" size="sm" className="lg:hidden" onClick={() => setMobileHistoryOpen(true)}>{t('History')}</Button>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin p-4 space-y-4">
          {messages.map((m) => (
            <motion.div key={m.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${m.role === 'user' ? 'bg-primary-600' : 'bg-gradient-primary'}`}>
                {m.role === 'user' ? <User className="w-4 h-4 text-white" /> : <Bot className="w-4 h-4 text-white" />}
              </div>
              {/* The squared corner points at the speaker's avatar. Logical
                  corners (start/end), so it still does in Arabic, where the
                  two sides swap. */}
              {/* dir="auto": a message runs in the direction of its own
                  language, so an English reply on an Arabic page (or the
                  reverse) keeps its punctuation and figures in place. */}
              <div dir="auto" className={`max-w-[75%] px-4 py-2.5 rounded-2xl text-sm ${m.role === 'user' ? 'bg-primary-600 text-white rounded-se-sm' : 'bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 rounded-ss-sm'}`}>
                {m.text}
              </div>
            </motion.div>
          ))}
          {typing && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-3">
              <div className="w-8 h-8 rounded-lg bg-gradient-primary flex items-center justify-center shrink-0"><Bot className="w-4 h-4 text-white" /></div>
              <div className="px-4 py-3 rounded-2xl bg-slate-100 dark:bg-slate-800 rounded-ss-sm flex gap-1">
                {[0, 1, 2].map((i) => (
                  <motion.span key={i} animate={{ y: [0, -4, 0] }} transition={{ duration: 0.6, repeat: Infinity, delay: i * 0.15 }} className="w-2 h-2 rounded-full bg-slate-400" />
                ))}
              </div>
            </motion.div>
          )}
        </div>

        {messages.length <= 1 && (
          <div className="px-4 pb-2 flex flex-wrap gap-2">
            {suggested.map((s) => (
              <button key={s} onClick={() => send(asked(s))} className="px-3 py-1.5 rounded-full text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-primary-50 dark:hover:bg-primary-500/10 hover:text-primary-600 transition">{t(s)}</button>
            ))}
          </div>
        )}

        <div className="p-4 border-t border-slate-100 dark:border-slate-800">
          {/* A microphone button sat here offering voice input. No speech code
              exists anywhere in the project, so it was a picture of a feature. */}
          <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="flex items-center gap-2">
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={t('Ask about your energy usage...')} dir="auto" className="flex-1 input-base h-11" />
            <Button type="submit" size="md" loading={typing} disabled={!input.trim()} leftIcon={<Send className="w-4 h-4" />}>{t('Send')}</Button>
          </form>
          {/* Said where it matters: in the other five languages a typed
              question is not understood (see the note above `suggested`). */}
          {!UNDERSTOOD.has(getLanguage()) && (
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{t('The assistant understands questions in English and Arabic.')}</p>
          )}
        </div>
      </Card>

      {/* Mobile history drawer */}
      <AnimatePresence>
        {mobileHistoryOpen && (
          <div className="lg:hidden fixed inset-0 z-50">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={() => setMobileHistoryOpen(false)} />
            <motion.div initial={{ x: slideFrom(280) }} animate={{ x: 0 }} exit={{ x: slideFrom(280) }} className="absolute end-0 top-0 bottom-0 w-72 bg-white dark:bg-slate-900 p-4">
              <div className="flex items-center justify-between mb-4">
                <p className="font-semibold text-slate-900 dark:text-slate-100">{t('History')}</p>
                <button onClick={() => setMobileHistoryOpen(false)} className="text-slate-400">{t('Close')}</button>
              </div>
              <Button fullWidth leftIcon={<Plus className="w-4 h-4" />} className="mb-4" onClick={startNewChat}>{t('New chat')}</Button>
              <div className="space-y-1">
                {historyList(openConversation)}
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
