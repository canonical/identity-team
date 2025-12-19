#!/usr/bin/env bash

charms=(
    "glauth-k8s-operator"
    "glauth-utils"
    "hook-service-operator"
    "hydra-operator"
    "identity-platform-admin-ui-operator"
    "identity-platform-login-ui-operator"
    "kratos-external-idp-integrator"
    "kratos-operator"
    "ldap-integrator"
    "oauth2-proxy-k8s-operator"
    "openfga-operator"
    "user-verification-service-operator"
)

rocks=(
    "glauth-rock"
    "hydra-rock"
    "kratos-rock"
    "oauth2-proxy-rock"
    "openfga-rock"
)

apps=(
    "hook-service"
    "identity-platform-admin-ui"
    "identity-platform-login-ui"
    "user-verification-service"
)

misc=(
    "canonical-identity-platform-docs"
    "cd-identity-core-infrastructure"
    "iam-bundle"
    "iam-bundle-integration"
    "identity-team"
)

repos=("${charms[@]}" "${rocks[@]}" "${apps[@]}" "${misc[@]}")
