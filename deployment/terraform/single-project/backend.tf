terraform {
  backend "gcs" {
    bucket = "terraform-training-387507-terraform-state"
    prefix = "sre-agent/dev"
  }
}
