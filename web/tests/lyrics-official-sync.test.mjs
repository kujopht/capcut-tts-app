import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test("lyricsData.ts contains 100% official lyrics without ASR hallucinations", () => {
  const filePath = path.resolve(__dirname, "../src/lib/lyricsData.ts");
  const content = fs.readFileSync(filePath, "utf-8");

  // Verify Imagine Dragons - Shots official lyrics (segmented into natural singing phrases)
  assert.ok(content.includes("Am I out of touch?"), "Shots Verse 1 line 1 correct");
  assert.ok(content.includes("Am I out of my place?"), "Shots Verse 1 line 2 correct");
  assert.ok(content.includes("When I keep saying"), "Shots keep saying correct");
  assert.ok(content.includes("That I'm looking for an empty space"), "Shots empty space correct");
  assert.ok(content.includes("Oh, I'm wishing you're here,"), "Shots wish you're here correct");
  assert.ok(content.includes("But I'm wishing you're gone"), "Shots wish you're gone correct");
  assert.ok(content.includes("I can't have you"), "Shots can't have you correct");
  assert.ok(content.includes("And I'm only gonna do you wrong"), "Shots do you wrong correct");
  assert.ok(content.includes("Oh, I'm gonna mess this up"), "Shots mess this up correct");
  assert.ok(content.includes("Oh, this is just my luck"), "Shots just my luck correct");
  assert.ok(content.includes("Over and over and over again"), "Shots over again correct");
  assert.ok(content.includes("In the meantime, we let it go"), "Shots meantime correct");
  assert.ok(content.includes("At the roadside that we used to know"), "Shots roadside correct");
  assert.ok(content.includes("We can let this drift away"), "Shots drift away line 1 correct");
  assert.ok(content.includes("Oh we let this drift away"), "Shots drift away line 2 correct");
  assert.ok(content.includes("I'm sorry for everything, oh, everything I've done"), "Shots bridge correct");
  assert.ok(content.includes("From the second that I was born"), "Shots loaded gun line 1 correct");
  assert.ok(content.includes("It seems I had a loaded gun"), "Shots loaded gun line 2 correct");
  assert.ok(content.includes("And then I shot, shot, shot"), "Shots chorus line 1 correct");
  assert.ok(content.includes("A hole through everything I loved"), "Shots chorus line 2 correct");
  assert.ok(content.includes("Am I out of luck?"), "Shots Verse 2 line 1 correct");
  assert.ok(content.includes("Am I waiting to break?"), "Shots Verse 2 line 2 correct");
  assert.ok(content.includes("taken for granted"), "Shots taken for granted correct");

  // Verify Professor Green - In the Shadow of the Sun official lyrics (segmented into natural singing phrases)
  assert.ok(content.includes("They say that life is always easier"), "Shadow opening correct");
  assert.ok(content.includes("After you let yourself come undone"), "Shadow come undone correct");
  assert.ok(content.includes("And I'll be waiting in the shadow of the sun"), "Shadow title hook correct");
  assert.ok(content.includes("She's in doubt but always been before"), "Shadow hook line 5 correct");
  assert.ok(content.includes("Close the curtains, what you waiting for?"), "Shadow hook line 6 correct");
  assert.ok(content.includes("And now we're keeping secrets 'til I'm in the ground"), "Shadow secrets in ground correct");
  assert.ok(content.includes("Keep your past your own, I don't care about before"), "Shadow rap verse 1 correct");
  assert.ok(content.includes("I don't wanna know your secrets, I wanna help you keep yours"), "Shadow help keep yours correct");
  assert.ok(content.includes("No one needs to, no one'll ever know what we do"), "Shadow what we do correct");
  assert.ok(content.includes("To a place where only we know,"), "Shadow only we know correct");
  assert.ok(content.includes("Where we escape from real life"), "Shadow escape real life correct");
  assert.ok(content.includes("And it feels good, and it feels nice"), "Shadow feels nice correct");
  assert.ok(content.includes("That we ain't yet, but we still might,"), "Shadow still might correct");
  assert.ok(content.includes("'Cause we go with it if it feels right"), "Shadow feels right correct");
  assert.ok(content.includes("And it feels, feels amazing"), "Shadow feels amazing correct");
  assert.ok(content.includes("Let go of fear,"), "Shadow let go of fear correct");
  assert.ok(content.includes("This can be a secret that we both keep"), "Shadow secret we both keep correct");
  assert.ok(content.includes("hidden behind the smiles we both wear"), "Shadow smiles correct");
  assert.ok(content.includes("On the walls we become two silhouettes"), "Shadow silhouettes correct");
  assert.ok(content.includes("As we close our eyes"), "Shadow close our eyes correct");
  assert.ok(content.includes("And let go of the lies that fill our heads"), "Shadow lies that fill our heads correct");
  assert.ok(content.includes("Let's light it up, live life in the moment"), "Shadow live life in the moment correct");
  assert.ok(content.includes("They can't see us, they can't judge us, it's just us"), "Shadow they can't judge us correct");
  assert.ok(content.includes("Finding treasure that's been on demise,"), "Shadow treasure on demise correct");
  assert.ok(content.includes("Building mountains in disguise"), "Shadow building mountains correct");
  assert.ok(content.includes("Chasing it, chasing it,"), "Shadow chasing it line 1 correct");
  assert.ok(content.includes("I don't know what I'm chasing is"), "Shadow chasing it line 2 correct");
  assert.ok(content.includes("All I know is I've been craving it,"), "Shadow craving it correct");
  assert.ok(content.includes("Ever since I had a taste of you"), "Shadow taste of you correct");
  assert.ok(content.includes("Life is what you make of it"), "Shadow what you make of it correct");
  assert.ok(content.includes("We're just there writing our own books"), "Shadow writing our own books correct");
  assert.ok(content.includes("Before you wave your fingers at us"), "Shadow wave your fingers correct");
  assert.ok(content.includes("You better make sure your hands are clean"), "Shadow hands are clean correct");
  assert.ok(content.includes("We all obey, our hands are tied"), "Shadow hands are tied correct");
  assert.ok(content.includes("I don't wanna say goodbye"), "Shadow say goodbye correct");

  // Verify elimination of all ASR phonetic mishears/hallucinations
  assert.ok(!content.includes("out of my veins"), "No 'out of my veins'");
  assert.ok(!content.includes("scholar"), "No 'scholar'");
  assert.ok(!content.includes("Sidefoot"), "No 'Sidefoot'");
  assert.ok(!content.includes("She's the tower"), "No 'She's the tower'");
  assert.ok(!content.includes("wee boat"), "No 'wee boat'");
  assert.ok(!content.includes("radical"), "No 'radical'");
  assert.ok(!content.includes("presence which we're waiting for"), "No 'presence which we're waiting for'");
});
