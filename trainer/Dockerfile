# =============================================================================
# AI Analyst Lab — TRAINER image
#
# The student image plus the three things a student must never have:
#   - the reference solution            /opt/trainer-default/solution/
#   - the hidden tests and questions    /opt/trainer-default/hidden/
#   - the grader                        /usr/local/bin/grade.py
#
# A separate image, not a ROLE switch on one image. sdv-ml-lab ships its answer
# key in every image and relies on the platform to decide who gets ROLE=trainer
# — and says of that: "a provisioning boundary, not a security one". Here the
# hidden tests ARE the assessment, and a student has a terminal, so the answers
# are simply not present in the image a student runs. `ROLE=trainer` on the
# student image finds nothing to seed and falls back to student.
#
# Build the student image first, then this one FROM it (context = the lab root):
#
#     docker build -t ai-analyst-lab:v1 .
#     docker build -f trainer/Dockerfile --build-arg BASE=ai-analyst-lab:v1 \
#                  -t ai-analyst-lab:v1-trainer .
#
# Push it to a repository students cannot pull from, or at least under a tag
# the student provisioning path never references.
#
# UNBUILT (no docker CLI on the authoring workstation).
# =============================================================================
ARG BASE=ai-analyst-lab:v1
FROM ${BASE}

# The solution is assignment-src/ itself: the complete, working assignment with
# its TODO markers still visible, so a trainer can see exactly which lines a
# student was asked to write.
COPY --chown=student:workspace assignment-src/ /opt/trainer-default/solution/
COPY --chown=student:workspace trainer/hidden/ /opt/trainer-default/hidden/
COPY --chown=student:workspace trainer/ANSWER-KEY.md trainer/RUBRIC.md trainer/answer-key.json \
     /opt/trainer-default/

# grade.py is the rubric as code; provision_student.py creates a database and a
# vector collection for a student (or for a grading run).
COPY scripts/grade.py /usr/local/bin/grade.py
COPY platform/provision_student.py /usr/local/bin/provision_student.py

RUN sed -i 's/\r$//' /usr/local/bin/grade.py /usr/local/bin/provision_student.py \
    && find /opt/trainer-default -name '*.sh' -exec sed -i 's/\r$//' {} \; \
    && find /opt/trainer-default -name '*.sh' -exec chmod +x {} \; \
    && find /opt/trainer-default -name '__pycache__' -type d -prune -exec rm -rf {} + \
    && rm -rf /opt/trainer-default/solution/output /opt/trainer-default/solution/.env \
    && chmod +x /usr/local/bin/grade.py /usr/local/bin/provision_student.py

# The entrypoint seeds /opt/trainer-default into <workspace>/trainer-only/ when
# ROLE=trainer and that directory exists - which is only here.
ENV ROLE=trainer
