# Classic attributions: common misattributions

Checked on 2026-10-17. This is the readable version of `misattributions.yaml`, which check BEH-15 and the citation judge use. The YAML holds the full record for each entry: matching terms, the original's metadata as confirmed in Crossref, the rule, and the quotes with their URLs that back each attribution. 43 of the 45 entries are verified. Two are marked likely, because their originals have no DOI or the sources do not pin the idea to one article. Re-check an entry before treating it as ground truth after April 2027.

## How to use it

When a draft credits a well-known finding or concept to a source, look the finding up by its terms and compare the cited work with the original and the common misattributions. **A match is a lead for the citation judge, not proof.** A paper can rightly cite a later source for a refinement, extension or estimate, such as Tversky and Kahneman (1992) for cumulative prospect theory. It can cite a review for an overview, or a reprint or translation next to the original date. So the judge first decides what the sentence claims: the origin of a concept or label, a specific number, or an experimental result. It then checks the cited work under the rules of `docs/DESIGN.md` section 7, quoting the passage or the search record. The failure codes come from case study 1:

- **S4, wrong source:** the claim is right but belongs to another work, such as a loss-aversion estimate credited to the 1979 paper.
- **S5, secondhand:** a review, column or popular book is cited as the origin.

Wrong years and swapped author orders of the right work are metadata errors under CIT-03. Failed replications fall under CIT-14 and retractions under CIT-05. A finding that is misdescribed or overstated is S2 or S3.

## The list

### Risk and uncertainty

| Finding | Original source | Common misattribution |
|---|---|---|
| St. Petersburg paradox, log utility (`bernoulli-expected-utility`) | Bernoulli (1738); English translation, *Econometrica* 1954 | "Bernoulli (1954)" as the date of the idea; Daniel Bernoulli credited with posing the problem, which Nicolaus Bernoulli posed in 1713 |
| Allais paradox (`allais-paradox`) | Allais (1953), *Econometrica* | Kahneman and Tversky (1979), who named the related certainty effect |
| Ellsberg paradox, ambiguity aversion (`ellsberg-paradox`) | Ellsberg (1961), *QJE* | Knight (1921) cited for the choice evidence |
| Prospect theory (`prospect-theory`) | Kahneman and Tversky (1979), *Econometrica* | Tversky and Kahneman (1992) as the origin; swapped author order |
| Loss-aversion coefficient of about 2.25 (`loss-aversion-coefficient`) | Tversky and Kahneman (1992), *Journal of Risk and Uncertainty* | Kahneman and Tversky (1979), whose value function is only qualitative; Tversky and Kahneman (1991) |

### Reference dependence and mental accounting

| Finding | Original source | Common misattribution |
|---|---|---|
| Endowment effect, the term (`endowment-effect-term`) | Thaler (1980), *JEBO* | Kahneman, Knetsch and Thaler (1990), or their 1991 *JEP* column |
| Mug experiments (`endowment-effect-mugs`) | Kahneman, Knetsch and Thaler (1990), *JPE* | Thaler (1980); Plott and Zeiler (2005) cited as confirming the gap |
| Status quo bias (`status-quo-bias`) | Samuelson and Zeckhauser (1988), *Journal of Risk and Uncertainty* | Kahneman, Knetsch and Thaler (1991); *Nudge* (2008) |
| Mental accounting, transaction utility (`mental-accounting`) | Thaler (1985), *Marketing Science* 4(3) | The 2008 reprint's volume or DOI under a 1985 date; Thaler (1999) as the origin |

### Judgment and heuristics

| Finding | Original source | Common misattribution |
|---|---|---|
| Anchoring and adjustment (`anchoring-heuristic`) | Tversky and Kahneman (1974), *Science* | Kahneman (2011); Ariely, Loewenstein and Prelec (2003) as the origin |
| Framing, the Asian disease problem (`framing-effect`) | Tversky and Kahneman (1981), *Science* | Kahneman and Tversky (1979) |
| Planning fallacy (`planning-fallacy`), likely | Kahneman and Tversky, technical report 1977, cited as 1979 | Buehler, Griffin and Ross (1994) as coining the term |
| Most drivers rate themselves above average (`better-than-average-drivers`) | Svenson (1981), *Acta Psychologica* | "93% of drivers" in general, though 93% is the US student sample's share |
| Dunning–Kruger effect (`dunning-kruger`) | Kruger and Dunning (1999), *JPSP* | "Dunning and Kruger (1999)"; read as low intelligence breeding overconfidence |
| Hot-hand fallacy (`hot-hand`) | Gilovich, Vallone and Tversky (1985), *Cognitive Psychology* | Cited as settled without Miller and Sanjurjo (2018); author order |

### Bounded rationality and cognition

| Finding | Original source | Common misattribution |
|---|---|---|
| Bounded rationality, satisficing (`bounded-rationality`) | Simon (1955), *QJE*; the term in *Models of Man* (1957); "satisficing" in Simon (1956) | Kahneman (2003) as the origin; 1955 given as the year the term was coined |
| System 1 and System 2 (`system-1-system-2`) | Stanovich and West (2000), *Behavioral and Brain Sciences* | Kahneman (2003, 2011) |
| Cognitive Reflection Test (`cognitive-reflection-test`) | Frederick (2005), *JEP* | Popular retellings of the bat-and-ball question |

### Time preference and self-control

| Finding | Original source | Common misattribution |
|---|---|---|
| Time inconsistency (`time-inconsistency-strotz`) | Strotz (1955, often cited as 1956), *Review of Economic Studies* | Laibson (1997) or O'Donoghue and Rabin (1999) as the origin; Kydland and Prescott (1977) |
| Hyperbolic discounting (`hyperbolic-discounting`), likely | Ainslie (1975), *Psychological Bulletin*; first human evidence Thaler (1981) | Laibson (1997) |
| Quasi-hyperbolic, beta-delta discounting (`quasi-hyperbolic-discounting`) | Phelps and Pollak (1968), *Review of Economic Studies* | Laibson (1997) as its inventor |
| Present-biased preferences, naive and sophisticated agents (`present-bias`) | O'Donoghue and Rabin (1999), *AER* | Laibson (1997); the review by Frederick, Loewenstein and O'Donoghue (2002) |
| Commitment savings account (`commitment-savings`) | Ashraf, Karlan and Yin (2006), *QJE* | Ariely and Wertenbroch (2002), now retracted; Thaler and Benartzi (2004) |
| Paying not to go to the gym (`gym-contracts`) | DellaVigna and Malmendier (2006), *AER* | DellaVigna and Malmendier (2004), *QJE* |
| Marshmallow test and later outcomes (`marshmallow-test`) | Shoda, Mischel and Peake (1990), *Developmental Psychology* | Mischel and Ebbesen (1970); cited without Watts, Duncan and Quan (2018) |

### Defaults and choice architecture

| Finding | Original source | Common misattribution |
|---|---|---|
| 401(k) automatic enrollment (`default-401k`) | Madrian and Shea (2001), *QJE* | *Nudge* (2008); Samuelson and Zeckhauser (1988) |
| Organ-donation defaults (`default-organ-donation`) | Johnson and Goldstein (2003), *Science* | *Nudge* (2008) and later reviews |
| Libertarian paternalism and nudges (`libertarian-paternalism-nudge`) | Thaler and Sunstein (2003), *AER Papers and Proceedings*; Sunstein and Thaler (2003) | *Nudge* (2008) as the origin of the term |
| Save More Tomorrow (`save-more-tomorrow`) | Thaler and Benartzi (2004), *JPE* | "Benartzi and Thaler (2004)"; Madrian and Shea (2001) |
| Choice overload, the jam study (`choice-overload-jam`) | Iyengar and Lepper (2000), *JPSP* | Schwartz (2004); cited as a general law despite a meta-analytic mean near zero |
| 1/n heuristic in retirement plans (`naive-diversification-1n`) | Benartzi and Thaler (2001), *AER* | DeMiguel, Garlappi and Uppal (2009), on 1/N portfolio performance |

### Behavioral finance

| Finding | Original source | Common misattribution |
|---|---|---|
| Equity premium puzzle (`equity-premium-puzzle`) | Mehra and Prescott (1985), *Journal of Monetary Economics* | Benartzi and Thaler (1995) |
| Myopic loss aversion (`myopic-loss-aversion`) | Benartzi and Thaler (1995), *QJE* 110(1): 73-92 | Mehra and Prescott (1985); Gneezy and Potters (1997) as the origin; pages given as 75-92 |
| Disposition effect (`disposition-effect`) | Shefrin and Statman (1985), *Journal of Finance* | Odean (1998) as naming it |
| Overconfidence and excessive trading (`overconfidence-trading`) | Barber and Odean (2000), *Journal of Finance*; gender test in Barber and Odean (2001), *QJE* | The two papers swapped |

### Social preferences and games

| Finding | Original source | Common misattribution |
|---|---|---|
| Ultimatum game (`ultimatum-game`) | Güth, Schmittberger and Schwarze (1982), *JEBO* | Thaler's 1988 column; Kahneman, Knetsch and Thaler (1986) |
| Dictator game (`dictator-game`) | Kahneman, Knetsch and Thaler (1986), *Journal of Business* | Forsythe et al. (1994) as the first; the 1986 *AER* fairness paper |
| Gift exchange (`gift-exchange`) | Akerlof (1982), *QJE* | Fehr, Kirchsteiger and Riedl (1993) as the origin; Gneezy and List (2006) as support for lasting effects |
| Inequity aversion (`inequity-aversion`) | Fehr and Schmidt (1999), *QJE*; ERC in Bolton and Ockenfels (2000), *AER* | The two models' specifications swapped |
| Conditional cooperation (`conditional-cooperation`) | Fischbacher, Gächter and Fehr (2001), *Economics Letters* | Fehr and Gächter (2000) |
| Altruistic punishment (`altruistic-punishment`) | Fehr and Gächter (2002), *Nature*; costly punishment in Fehr and Gächter (2000), *AER* | The 2000 paper cited for the term; "Gächter and Fehr (2000)" |

### Markets, labor and the field

| Finding | Original source | Common misattribution |
|---|---|---|
| Winner's curse (`winners-curse`) | Capen, Clapp and Campbell (1971), *Journal of Petroleum Technology* | Thaler's 1988 column |
| Cab drivers' daily income targets (`cab-driver-labor-supply`) | Camerer, Babcock, Loewenstein and Thaler (1997), *QJE* | Farber (2005, 2008) cited as support, though his results go against it |

### Contested psychology findings

| Finding | Original source | Common misattribution |
|---|---|---|
| Ego depletion (`ego-depletion`) | Baumeister, Bratslavsky, Muraven and Tice (1998), *JPSP* | Cited as established despite the multilab replication of Hagger et al. (2016) |
| Money priming (`money-priming`) | Vohs, Mead and Goode (2006), *Science* | Confused with Caruso et al. (2013); cited as established |
