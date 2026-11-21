from wtforms import Form, StringField, IntegerField, BooleanField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, Regexp

COUNTRIES = [("us", "United States"), ("de", "Germany"), ("jp", "Japan"), ("br", "Brazil")]
GENDERS = [("f", "Female"), ("m", "Male"), ("x", "Other")]

def make_form(n):
    """Realistic account/profile form with n fields, modelled on production signup forms."""
    attrs = {}
    patterns = [
        ("first_name", StringField, [DataRequired(), Length(min=1, max=60)]),
        ("last_name", StringField, [DataRequired(), Length(min=1, max=60)]),
        ("email", StringField, [DataRequired(), Length(min=6, max=254)]),
        ("username", StringField, [DataRequired(), Length(min=3, max=32), Regexp(r"^[a-z0-9_]+$")]),
        ("password", StringField, [DataRequired(), Length(min=8, max=128)]),
        ("city", StringField, [Optional(), Length(max=80)]),
        ("postal_code", StringField, [Optional(), Length(max=16)]),
        ("phone", StringField, [Optional(), Length(max=32)]),
        ("website", StringField, [Optional(), Length(max=200)]),
        ("company", StringField, [Optional(), Length(max=120)]),
        ("job_title", StringField, [Optional(), Length(max=120)]),
        ("bio", TextAreaField, [Optional(), Length(max=500)]),
    ]
    num = [
        ("age", [DataRequired(), NumberRange(min=13, max=120)]),
        ("seats", [DataRequired(), NumberRange(min=1, max=500)]),
        ("team_size", [Optional(), NumberRange(min=0, max=10000)]),
        ("years_experience", [Optional(), NumberRange(min=0, max=80)]),
    ]
    i = 0
    fields = []
    while len(fields) < n:
        if len(fields) % 3 == 2 and num:
            name, vals = num[i % len(num)]
            fields.append((f"{name}_{len(fields)}", IntegerField, vals))
        else:
            name, cls, vals = patterns[i % len(patterns)]
            fields.append((f"{name}_{len(fields)}", cls, vals))
        i += 1
    fields = fields[:n]
    if n >= 6:
        fields[-3] = ("country", SelectField, [DataRequired()], dict(choices=COUNTRIES))
        fields[-2] = ("gender", SelectField, [Optional()], dict(choices=GENDERS))
        fields[-1] = ("terms", BooleanField, [DataRequired()])
    for name, cls, vals, *rest in fields:
        kwargs = rest[0] if rest else {}
        attrs[name] = cls(validators=vals, **kwargs)
    attrs["_spec"] = fields
    return type("ProfileForm", (Form,), attrs)

def payload_for(form, valid=True):
    form = form if hasattr(form, "_spec") else type(form)
    from wtforms import StringField, IntegerField, BooleanField, SelectField, TextAreaField
    p = {}
    for i, (name, cls, vals, *rest) in enumerate(form._spec):
        if issubclass(cls, StringField):
            v = {"username": "ada_99", "email": "ada@example.com", "password": "s3cret-passphrase",
                 "website": "https://example.com", "postal_code": "10115", "phone": "+49 30 1234567"}.get(
                     name.split("_")[0] + ("_" + name.split("_")[1] if name.startswith("first") or name.startswith("last") else ""), "Ada Lovelace")
            p[name] = v
        elif issubclass(cls, IntegerField):
            p[name] = "30"
        elif issubclass(cls, SelectField):
            p[name] = (rest[0] if rest else {}).get("choices", [("x",)])[0][0]
        elif issubclass(cls, BooleanField):
            p[name] = "y"
        elif issubclass(cls, TextAreaField):
            p[name] = "hello world " * 4
    if not valid:
        for i, (name, cls, vals, *rest) in enumerate(form._spec):
            if i % 3 == 0 and issubclass(cls, StringField):
                p[name] = ""
            elif i % 5 == 0 and name.startswith("username"):
                p[name] = "Bad Name!"
    return p
