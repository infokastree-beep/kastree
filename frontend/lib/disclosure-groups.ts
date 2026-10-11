/**
 * Group pack disclosure questions and describe a mark-remaining-no confirmation.
 * Unanswered stays unanswered until the server says the write succeeded.
 */

export type DisclosureAnswerState = "yes" | "no" | "unanswered";

export type DisclosureQuestion = {
  flag_name: string;
  question: string;
  group: string;
  note: string | null;
  answer: DisclosureAnswerState;
};

export type DisclosureGroup = {
  group: string;
  note: string | null;
  answered: number;
  unanswered: number;
  questions: DisclosureQuestion[];
};

export type RemainingGroup = {
  group: string;
  count: number;
};

export function groupDisclosureQuestions(
  questions: readonly DisclosureQuestion[],
): DisclosureGroup[] {
  const groups: DisclosureGroup[] = [];
  for (const question of questions) {
    const current = groups.find((group) => group.group === question.group);
    if (current) {
      current.questions.push(question);
    } else {
      groups.push({
        group: question.group,
        note: null,
        answered: 0,
        unanswered: 0,
        questions: [question],
      });
    }
  }
  return groups.map((group) => {
    const notes = group.questions
      .map((question) => question.note)
      .filter((note): note is string => typeof note === "string" && note.length > 0);
    const uniqueNotes = notes.filter((note, index) => notes.indexOf(note) === index);
    const answered = group.questions.filter((question) => question.answer !== "unanswered").length;
    return {
      ...group,
      note: uniqueNotes.length === 1 ? uniqueNotes[0]! : null,
      answered,
      unanswered: group.questions.length - answered,
    };
  });
}

export function remainingNoSummary(questions: readonly DisclosureQuestion[]): {
  groups: RemainingGroup[];
  total: number;
} {
  const groups = groupDisclosureQuestions(questions)
    .filter((group) => group.unanswered > 0)
    .map((group) => ({ group: group.group, count: group.unanswered }));
  return {
    groups,
    total: groups.reduce((sum, group) => sum + group.count, 0),
  };
}

export function noteHref(yearEndId: string, note: string): string {
  return `/year-ends/${yearEndId}/draft?section=notes&note=${encodeURIComponent(note)}`;
}

/** A successful write is the only path that turns unanswered into No. */
export function answerAfterMark(
  question: DisclosureQuestion,
  postedFlagIds: readonly string[] | null,
): DisclosureAnswerState {
  if (
    postedFlagIds != null &&
    question.answer === "unanswered" &&
    postedFlagIds.includes(question.flag_name)
  ) {
    return "no";
  }
  return question.answer;
}
