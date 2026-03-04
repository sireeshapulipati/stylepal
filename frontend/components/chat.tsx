"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

type Message = {
  role: "user" | "assistant";
  content: string;
  outfitPlan?: {
    description: string;
    items: number[];
    options?: { description: string; items: number[] }[];
  };
  reasoning?: string;
  isInformational?: boolean;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 180_000; // 3 min - outfit requests need get_wardrobe + RAG + weather + agent

export function Chat() {
  const [threadId, setThreadId] = useState(() => `stylepal-chat-${Date.now()}`);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  function startNewChat() {
    setThreadId(`stylepal-chat-${Date.now()}`);
    setMessages([]);
    setError(null);
  }

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendMessage(query: string) {
    if (!query.trim() || loading) return;

    setInput("");
    setMessages((m) => [...m, { role: "user", content: query }]);
    setLoading(true);
    setError(null);

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
      const res = await fetch(`${API_URL}/stylist/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          thread_id: threadId,
        }),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      const outfit = data.outfit_plan?.description ?? "";
      const reasoning = data.reasoning ?? "";
      const content =
        outfit || reasoning
          ? outfit
            ? reasoning
              ? `${outfit}\n\n${reasoning}`
              : outfit
            : reasoning
          : "The stylist couldn't generate a response. Try rephrasing your question or ask again.";

      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content,
          outfitPlan: data.outfit_plan,
          reasoning,
          isInformational: data.is_informational,
        },
      ]);
    } catch (err) {
      const message =
        err instanceof Error && err.name === "AbortError"
          ? "Request timed out. The stylist is taking longer than usual—try again or simplify your query."
          : err instanceof Error
            ? err.message
            : "Request failed";
      setError(message);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: `Sorry, something went wrong: ${message}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const query = input.trim();
    if (!query) return;
    await sendMessage(query);
  }

  async function handleFeedback(feedback: "thumbs_up" | "thumbs_down") {
    const query = feedback === "thumbs_up" ? "👍" : "👎";
    await sendMessage(query);
  }

  async function handlePickOption(option: 1 | 2) {
    await sendMessage(`Pick Option ${option}`);
  }

  return (
    <div className="chat-layout flex h-screen flex-col">
      <header className="border-b border-border bg-card px-4 py-3 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h1 className="text-lg font-semibold text-foreground">
              Stylepal — Hi, Maya
            </h1>
            <p className="text-sm text-muted-foreground">
              A trusted style companion that starts with your wardrobe
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={startNewChat}
            disabled={loading}
            className="border-primary/30 text-primary hover:bg-secondary hover:text-secondary-foreground"
          >
            New Chat
          </Button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto p-4">
        <div className="mx-auto max-w-2xl space-y-4">
          {messages.length === 0 && (
            <Card className="border-dashed border-primary/25 bg-card/80">
              <CardContent className="py-8 text-center text-muted-foreground">
                <p className="mb-2">Try asking:</p>
                <ul className="space-y-1 text-sm">
                  <li>• &quot;Outfit for a client meeting tomorrow&quot;</li>
                  <li>• &quot;Casual Friday look&quot;</li>
                  <li>• &quot;Something for a dinner date&quot;</li>
                </ul>
              </CardContent>
            </Card>
          )}

          {messages.map((msg, i) => (
            <div key={i} className="space-y-2">
              <div
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <Card
                  className={`max-w-[85%] ${
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground shadow-md"
                      : "bg-card border-primary/20 shadow-sm"
                  }`}
                >
                  <CardContent className="py-3 px-4">
                    {msg.role === "assistant" && msg.outfitPlan?.description && !msg.isInformational ? (
                      <div className="space-y-2">
                        <p className="font-medium">OUTFIT</p>
                        <pre className="whitespace-pre-wrap text-sm">
                          {msg.outfitPlan.description}
                        </pre>
                        {msg.reasoning && (
                          <>
                            <p className="font-medium pt-2">REASONING</p>
                            <p className="text-sm text-muted-foreground">
                              {msg.reasoning}
                            </p>
                          </>
                        )}
                      </div>
                    ) : (
                      <p className="whitespace-pre-wrap text-sm">{msg.content}</p>
                    )}
                  </CardContent>
                </Card>
              </div>
              {msg.role === "assistant" &&
                msg.outfitPlan?.description &&
                i === messages.length - 1 &&
                !loading &&
                !msg.isInformational &&
                !msg.outfitPlan.description.includes("What would you like to change?") &&
                !msg.outfitPlan.description.startsWith("No problem!") &&
                !msg.outfitPlan.description.startsWith("Thanks for the feedback") &&
                !msg.outfitPlan.description.startsWith("Thanks!") &&
                !msg.outfitPlan.description.startsWith("Got it!") && (
                  <div className="flex justify-start gap-2 pl-1 flex-wrap">
                    {msg.outfitPlan.options && msg.outfitPlan.options.length >= 2 ? (
                      <>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handlePickOption(1)}
                          disabled={loading}
                          className="gap-1 border-primary/30 text-primary hover:bg-secondary"
                        >
                          Pick Option 1
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handlePickOption(2)}
                          disabled={loading}
                          className="gap-1 border-primary/30 text-primary hover:bg-secondary"
                        >
                          Pick Option 2
                        </Button>
                      </>
                    ) : (
                      <>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleFeedback("thumbs_up")}
                          disabled={loading}
                          className="gap-1 border-primary/30 text-primary hover:bg-secondary"
                        >
                          👍 Thumbs up
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleFeedback("thumbs_down")}
                          disabled={loading}
                          className="gap-1 border-primary/30 text-primary hover:bg-secondary"
                        >
                          👎 Thumbs down
                        </Button>
                      </>
                    )}
                  </div>
                )}
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <Card className="bg-card border-primary/20 shadow-sm">
                <CardContent className="py-3 px-4">
                  <span className="animate-pulse text-sm text-muted-foreground">
                    Thinking...
                  </span>
                </CardContent>
              </Card>
            </div>
          )}

          {error && (
            <p className="text-center text-sm text-destructive">{error}</p>
          )}

          <div ref={scrollRef} />
        </div>
      </div>

      <form
        onSubmit={handleSubmit}
        className="border-t border-border bg-card p-4 shadow-[0_-4px_12px_-4px_rgba(0,0,0,0.05)]"
      >
        <div className="mx-auto flex max-w-2xl gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask for an outfit suggestion..."
            disabled={loading}
            className="flex-1 border-primary/25 bg-transparent focus-visible:border-primary"
          />
          <Button
            type="submit"
            disabled={loading}
            className="bg-primary hover:bg-primary/90"
          >
            Send
          </Button>
        </div>
      </form>
    </div>
  );
}
