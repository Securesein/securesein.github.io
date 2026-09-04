---
title: "Tokens: the one idea that explains most of AI's odd behaviour"
description: "Why a model that can explain quantum tunnelling cannot count the letters in strawberry, why long conversations get slow and expensive, and why Dutch costs more than English. It all comes back to the very first thing that happens to your text."
pubDate: 2026-09-04
tags: ["models"]
author: "sebastiaan"
section: "fundamentals"
---

![A sentence being cut into eight token tiles, each with its own integer ID](/images/tokens-the-one-idea-that-explains-most-of-ai-s-odd-behaviour/hero.png)

How many times does the letter *r* appear in *strawberry*? Ask a model that can walk you through quantum tunnelling, and there is a fair chance it says two. For a long time I filed that sort of thing under *AI is weird* and moved on.

It is not weird. It is a predictable consequence of the very first thing that happens to your text, before the model does anything clever at all. That step is called **tokenization**, and once you see it, a pile of unrelated-looking mysteries collapses into a single explanation: the line items on your invoice, the *prompt is too long* error, the assistant forgetting what you agreed twenty messages ago, the fact that your Dutch prompt costs more than the English one — and the strawberry.

So let us take the whole thing apart, in three moves: where the pieces come from, what the model does with them, and what they cost you. No prior AI knowledge needed.

## First, the short answer

A token is the unit a language model reads and writes. Not a character, not a word, but something in between: a frequent fragment of text. The word `Tokenization` may well arrive at the model as two tokens, `Token` and `ization`.

Every model comes with a fixed list of these fragments, called its **vocabulary** — typically between 32,000 and a few hundred thousand entries. Your text gets covered with entries from that vocabulary, and each one is swapped for its number. The model only ever sees the numbers.

Two questions do all the work from here. Where does that vocabulary come from, and why does it contain such odd pieces? That is the next section, and it is worth the detour, because every strange thing a model does with letters, numbers and languages comes straight out of how the list was built.

## Why nobody chose words, and nobody chose letters

The word *token* is much older than the technology, and its history is not trivia — it is three separate fields walking into the same problem: before you can compute anything about language, you have to decide what counts as one unit.

It starts in philosophy of language, with the **type–token distinction**. Take *the cat sat on the mat*: how many words? Six, if you count occurrences. Five, if you count distinct words, because *the* appears twice. The occurrences are tokens; the distinct entries are types. Corpus linguistics has measured text this way for decades, and a model’s vocabulary is still, in exactly this sense, a list of types.

Then computing borrowed it. Every compiler since the late 1950s starts with *lexical analysis*: a scanner reads source code character by character and emits tokens. The statement `total = price * 3;` becomes six of them — identifier, assignment, identifier, operator, number, semicolon — so that the rest of the compiler never has to think about characters again. Modern AI tokenization sits in exactly that spot in the pipeline. The difference is everything else: a compiler’s token rules are written by hand from a formal grammar, while a model’s are learned from data and correspond to nothing grammatical at all.

The third thread is Claude Shannon, who in 1948 modelled English as a sequence of symbols where each one can be guessed, imperfectly, from what came before. That is still exactly what a language model does. Shannon also ran straight into the question we are circling: he tried it with letters, and he tried it with words, and neither is comfortable. Letters give you a tiny alphabet but very long sequences. Words give you much more meaning per symbol, but a vocabulary that never stops growing.

For decades the field went with words anyway, because it is the obvious choice: split on spaces and punctuation, give every word an entry. It breaks in three ways, and if you work in Dutch you will recognise all of them.

- **The vocabulary explodes.** Any serious corpus has hundreds of thousands of word forms, and compounding languages make it hopeless. *Arbeidsongeschiktheidsverzekering* is a perfectly ordinary word that no fixed list will ever contain.
- **Unknown words are destroyed.** Anything missing from the list becomes a single placeholder. Surnames, product codes, typos, new jargon: all the same meaningless marker, and the information is simply gone.
- **Nothing is shared.** *walk*, *walks*, *walked* and *walking* are four unrelated entries. The model learns each from scratch and learns nothing about the relationship.

So try the opposite extreme: one token per character. Now nothing is ever unknown, because every string is spellable. But your sequences become four or five times longer, which costs compute on every single word, and the model has to rediscover spelling before it can learn anything else.

Stuck between a unit that is too big and a unit that is too small, the escape came from a genuinely unexpected direction: **file compression**.

## How the vocabulary actually gets built

In 1994, Philip Gage published Byte Pair Encoding, a compression trick with nothing to do with language. The rule fits in one line: **find the two symbols that most often sit next to each other, and add that combination to your list as one new symbol.** Then do it again. In 2016 it was pointed at machine translation to deal with rare words, and the modern tokenizer was born.

Note the word *add*. Nothing gets thrown away, and that turns out to matter enormously later on. The list only ever grows.

BPE is trained on text — normally billions of words. To do it by hand, here is a corpus of exactly sixteen:


```text
newest  low  widest  newest  lower  low  newest  widest
low  newest  lower  newest  low  widest  newest  low
```

Step zero is to count what is in there: *newest* appears 6 times, *low* 5, *widest* 3, *lower* 2. Those four numbers are the fuel for everything that follows, because they decide which pair gets merged first. Then write every word out as separate characters — at this point the vocabulary is nothing but the alphabet — and start merging.

![A table of four BPE merges: the pair merged each round, the corpus after the merge, and the fragment added to the vocabulary, ending with the vocabulary of ten characters plus es, est, lo and low](/images/tokens-the-one-idea-that-explains-most-of-ai-s-odd-behaviour/bpe.png)

*Every round adds one entry. The corpus gets shorter; the vocabulary gets longer.*

That first count of 9 for `e`+`s` is worth pausing on, because it is where the frequencies earn their keep: the pair sits inside *newest* (6 occurrences) and inside *widest* (3), and 6 plus 3 beats every other pair in the corpus. A pair that only appears in *lower* is worth 2 and will wait a very long time for its turn.

Two things in that table surprised me when I first worked through it, and they are the two things worth taking away.

- **Merges stack.** `es` is a pair of letters, but `est` is that pair plus a letter, and `low` is a pair plus a letter again. After a few rounds you are merging chunks with chunks, which is how you end up with fragments of eight characters — and eventually with whole words as single entries.
- **The alphabet never leaves.** After four merges the vocabulary holds `l`, `o`, `w` *and* `low`. The letters are not replaced by the fragments built out of them; they sit alongside them, and they are the reason nothing is ever unrepresentable.

Which gives you the payoff at the bottom of that table. The word *lowest* never appeared in our corpus — the tokenizer has genuinely never seen it. Apply the merges in the order they were learned, and it still comes out as `low` + `est`: two known tokens, no information lost. A word-level vocabulary would have thrown it away as unknown, and a character-level one would have spent six tokens on it.

Scale that up — billions of words, tens of thousands of merges — and you get the deal every modern tokenizer offers: **frequency becomes efficiency.** The more often a word appeared in the training text, the fewer tokens it costs you today. Everything rare still works; it just costs more pieces.

![Four milestones: Shannon’s information theory in 1948, compiler lexers from 1957 to 1975, the word-token era of the 1990s, and byte pair encoding in 1994](/images/tokens-the-one-idea-that-explains-most-of-ai-s-odd-behaviour/timeline_a.png)

*Three fields walking into the same problem, and the compression trick that solved it.*

The refinements since then are variations on that same idea. **WordPiece** (2012, later the tokenizer behind BERT) picks merges by how much they improve the model’s fit rather than by raw frequency. **SentencePiece** (2018) drops the assumption that words are separated by spaces at all, which matters enormously for Japanese, Chinese and Thai. And in 2019 GPT-2 applied BPE to raw **bytes** instead of characters, so with all 256 byte values in the starting alphabet, any script, any emoji and any corrupted file fragment became representable. The unknown-word problem was finally dead.

![Four milestones: WordPiece in 2012, sub-words in neural machine translation in 2016, SentencePiece in 2018, byte-level tokenization from 2019 onwards](/images/tokens-the-one-idea-that-explains-most-of-ai-s-odd-behaviour/timeline_b.png)

*All four of these are still in production today.*

Keep one sentence from all of this, because the rest of the post leans on it: **a vocabulary is a compression scheme fitted to a pile of training text.** It is not a grammar, not a dictionary, and not a theory of language. Whenever a split looks strange, that is why.

## What actually happens to your sentence

Training is over. The vocabulary is finished, frozen, and shipped with the model — it never changes while you use it. So what happens when you type?

Three things, in order: your text gets covered with entries from the vocabulary, each entry is swapped for its number, and each number is used to look up a list of numbers that carries the meaning. Those are three different objects and it is worth keeping them apart.

| What you have | What it is |
| --- | --- |
| `Token` | A piece of text — an entry in the vocabulary. Single characters count too: a token is any entry, whatever its length. |
| `3404` | An address — nothing more than the position of that entry in the vocabulary. |
| `[0.02, -0.31, …]` | The meaning — a long list of numbers, learned during training, found at that address. |

Start with the covering. There is usually more than one way to cover the same text, because the alphabet is still in there:


```text
[Token][ization]        2 tokens   <- the tokenizer picks this
[Tok][en][iz][ation]    4 tokens
[T][o][k][e][n][...]   12 tokens
```

All three are valid. Fewer tokens means less compute and a smaller bill, so the tokenizer goes for the cheapest covering it can build — which is exactly why the frequent fragments from training are worth having.

Spaces are the first thing that trips people up: they belong *inside* tokens rather than separating them. `Hello` and `␣Hello` (with a leading space) are two different entries with two different numbers, and so are `hello` and `Hello`. A stray space in a prompt is not as cosmetic as it looks.

Then the numbers. If `Token` is entry 3404 in the vocabulary, its number is 3404 — sort the list differently and it would have a different number. So the number carries no meaning at all: token 3404 is not *more* than token 481, and 3404 and 3405 have nothing to do with each other. It is a house number.

What it is for is the lookup. The number selects a row from the **embedding matrix**: one row per vocabulary entry, a few thousand columns wide, every value learned during training. *That* row is where meaning lives. Fragments used in similar contexts drift towards similar rows, which is how a model ends up treating *doctor* and *physician* as related without anyone ever saying so.

![Four layers: the raw sentence, the tokens it is cut into, the integer ID of each token, and the embedding vector each ID selects](/images/tokens-the-one-idea-that-explains-most-of-ai-s-odd-behaviour/text_to_vectors.png)

*Characters become pieces, pieces become addresses, addresses become meaning.*

From there the model does one thing, extremely well. Given the sequence so far, it produces a score for **every single entry in the vocabulary**: how likely is each one to come next? Those scores become probabilities, one token gets picked, it is appended to the sequence — and the whole thing runs again.

![The generation loop: your text, tokenizer, token IDs, model, scores over the vocabulary, one token picked, and the result fed back to the start](/images/tokens-the-one-idea-that-explains-most-of-ai-s-odd-behaviour/loop.png)

*Generation is a loop, and it runs exactly once per token.*

This loop is visible in your daily use. Replies stream because they are genuinely produced piece by piece. Speed is quoted in *tokens per second*, because that is the unit of work. A length limit has to be a token count, because tokens are the only thing being counted.

One last mechanism, and it is the bridge to the money. Real vocabularies hold more than the alphabet and the merges: there is also a handful of **special tokens** that never come from text, put in by hand rather than found by merging. Markers for the start of a document, the end of a turn, the boundary between roles. Because a model does not receive a list of messages — it receives one flat sequence of tokens in which the conversation has been encoded, roughly like this:


```text
<start>system     You are a helpful assistant. <end>
<start>user       What is a token? <end>
<start>assistant
```

The model continues from there until it emits the end-of-turn token, which is how the app knows the reply is finished. Roles and system prompts are not features of the model. They are a convention, written in tokens — and they are on the bill like everything else.

## Back to the strawberry

We now have everything needed to explain the odd behaviour, because a vocabulary built from frequency does not line up with anything a human would pick.

- **Letters are barely visible.** Asked about the *r*s in *strawberry*, the model is not looking at ten letters. It is looking at two or three tokens whose internal spelling it only ever learned indirectly. Reversing strings, counting characters and writing acrostics are all harder than they look, for the same reason.
- **Arithmetic starts at a disadvantage.** Long numbers split into chunks that ignore place value, so *1234* may arrive as two pieces. Digit alignment, the thing that makes written arithmetic work at all, is not handed to the model for free.
- **Your language decides your bill.** Frequency becomes efficiency, and the training text was dominated by English — so English compresses best. The same content in Dutch typically needs about a third more tokens; scripts without spaces need considerably more per character.
- **Structured text is expensive.** Code, JSON, YAML, GUIDs, hashes and base64 fragment heavily, because random-looking strings share no frequent chunks with anything. They fall back on the alphabet, which always works and always costs.

![Bar chart of tokens per 100 characters: English prose lowest, then Dutch prose and Python code, then JSON, then serial numbers, with Japanese highest](/images/tokens-the-one-idea-that-explains-most-of-ai-s-odd-behaviour/efficiency.png)

*Identical character counts, very different token counts. Treat these as orders of magnitude rather than measurements — the exact numbers depend on the tokenizer.*

## What tokens cost you in a chatbox

Which brings us to the practical half, where all of the above turns into limits, latency and money.

The **context window** is the maximum number of tokens a model can hold in view at once. Not messages, not characters, and it covers everything simultaneously: the system prompt, the whole conversation, your attachments, any search or tool results, plus the reply being written.

For English prose, one token is roughly four characters or three quarters of a word, so 1,000 tokens is around 750 words — a page and a half. A 100-page report lands somewhere around 50,000 to 70,000 tokens. Today’s models range from tens of thousands of tokens to well over a million, and that is the fastest-moving number in the industry, so check the docs for whatever you are actually using.

Here is the part I wish I had understood years earlier: **the model is stateless.** It remembers nothing between calls. The conversation is an illusion maintained by the application, which re-sends the entire transcript every single turn. So your one-line follow-up in a long thread is not one line — it is the system prompt, plus every message either of you has written, plus your line, all processed again before a single new token appears.

![Stacked bar chart showing input tokens per turn growing from 950 at turn 1 to 8,650 at turn 15, approaching the context window limit](/images/tokens-the-one-idea-that-explains-most-of-ai-s-odd-behaviour/context.png)

*The cost of turn 15 is not the cost of turn 15’s message.*

Three things follow, and all three are things you have probably felt. Long conversations get slower and pricier per turn. When the transcript nears the limit something has to be dropped or summarised, which is precisely when an assistant starts *forgetting* what you agreed at the start. And opening a fresh chat for a new topic is not just tidier — it is cheaper and usually sharper, because the model is no longer reading thousands of irrelevant tokens.

Two more bits of economics worth knowing. **Output costs more than input**, usually several times more per token, for a mechanical reason rather than a commercial one: input can be processed in one parallel pass, while output has to be generated one token at a time, each requiring a full pass through the model. Reading is cheap; writing is expensive. And **prompt order matters**, because the internal state for an unchanged prefix can be cached and reused. Put the stable material — instructions, reference documents, long examples — at the front and leave it alone; put the variable part at the end. Change one character near the top and the whole cache is gone.

Then the small print, which is all token arithmetic once you know to look for it:

- Rate limits are usually **tokens per minute**, not requests per minute. One fat attachment can eat the budget of dozens of short questions.
- Input and output share the same window, so **leave room to answer**. If your input nearly fills it, there is nowhere for the reply to go — and a maximum output length set too low is why a reply stops mid-sentence.
- **Reasoning tokens count.** Models that think before answering generate intermediate tokens that are billed and consume the window, even when hidden. A short answer can be an expensive one.
- **Images and audio become tokens too.** A picture is converted into a grid of patch tokens, audio into frame tokens. That screenshot has a price, and a full-resolution one costs more than a crop.

### Rules of thumb worth keeping

| Rule of thumb | What it means in practice |
| --- | --- |
| 1 token ≈ 4 characters ≈ 0.75 words | English prose only. Fine for an estimate, never for a hard limit. |
| 1 page ≈ 500–700 tokens | A 100-page PDF is a serious chunk of most context windows. |
| Dutch, German ≈ 1.3–1.5× English | Same meaning, more tokens. Budget for it in non-English work. |
| Code and JSON beat prose for weight | Config files and logs burn context faster than you expect. |
| IDs, hashes and GUIDs are worst case | Roughly two characters per token. Don’t paste them in bulk. |
| Output costs more than input | Ask for the shortest useful answer, and say how long you want it. |
| Stable material goes first | It lets caching work and keeps your instructions out of the truncation zone. |
| Measure, don’t guess | Every model has its own tokenizer. Use the vendor’s counting tool when it matters. |

## So

A token is a compromise. Characters are too small to be efficient, words are too many to enumerate, so we settled on frequent fragments discovered by a compression algorithm — an idea assembled from a philosophical distinction, a compiler phase and an information-theoretic view of text.

It is also, frankly, one of the least elegant parts of the stack, and people are working on removing it: byte-level models that learn where to draw the boundaries themselves, rather than being handed a finished vocabulary. Promising, not yet the default. For the foreseeable future, tokens are what you get billed for.

Which is the point. Tokens are the metre of the AI world, and every merge in that little table is still visible in your invoice. Once you can think in them, the pricing, the limits, the drifting long threads and the miscounted strawberry all stop being mysterious and turn into arithmetic — and arithmetic you can plan around.

### Further reading

- C. E. Shannon, *A Mathematical Theory of Communication* (1948)
- P. Gage, *A New Algorithm for Data Compression* (1994) — the original BPE
- R. Sennrich, B. Haddow & A. Birch, *Neural Machine Translation of Rare Words with Subword Units* (2016)
- T. Kudo & J. Richardson, *SentencePiece* (2018)
- A. Radford et al., *Language Models are Unsupervised Multitask Learners* (2019) — byte-level BPE
