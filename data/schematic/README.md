# Typical-application data for schematics

What each datasheet says must sit around the part in a schematic: supply pins and their ground return,
external components (decoupling, pull-ups, series resistors, DC blocking, filters), and how to handle unused or
special pins. Used by *Convert to schematic* in the application workspace. One file per source group, keyed by
datasheet file name (the `datasheet:` field of the parts in `data/real/*.yaml`).

Only what the datasheet states. Every item carries a short verbatim `quote` from the datasheet text and the `page`
where the text has page markers. Nothing is inferred from general practice; if a datasheet does not state
external components, `components: []` and say so in `notes`. Check a file with `python tools/check_typical.py`.

```yaml
covers: [data/real/skyworks_si86.yaml]     # real-data files whose parts this file covers
datasheets:
  - datasheet: si864x-datasheet.pdf        # as in the parts' `datasheet:` field
    doc: "Si864x datasheet, Rev 1.8"       # title and revision as printed
    supplies:                              # each supply pin, its ground return, stated operating range
      - {pin: VDD1, ground: GND1, range_v: [2.5, 5.5], page: 12, quote: "..."}
    components:                            # one component per pin matching `pins`
      - kind: capacitor                    # capacitor | resistor | ferrite | inductor | diode | crystal | tvs | zener
        value: "0.1 µF"                    # as stated, with unit; "" if the datasheet gives none
        pins: '^VDD[12]$'                  # Python regex on pin names as used in the parts' pinout
        to: GND                            # other end: a pin name of the part, or a net: GND (the pin's own ground
                                           # return from `supplies`), VDD (the pin's supply), VIO, RF, ANTENNA, LOAD
        series: false                      # true = in series between the pin and its outside connection
        required: true                     # false = recommended / optional / "may"
        note: "as close to the pin as possible"
        page: 20
        quote: "verbatim, <= 30 words, copied from the datasheet text"
    pin_rules:                             # unused / special pins
      - pins: '^EN[12]$'
        rule: "internal pull-up: floating = outputs enabled; drive low to disable"
        page: 8
        quote: "..."
    notes: "e.g. GND1 and GND2 must stay separate; nothing stated about external components beyond decoupling"
```
