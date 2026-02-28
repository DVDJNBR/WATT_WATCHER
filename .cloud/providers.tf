terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  # Local backend for now — switch to Azure Blob for team/CI usage
  # backend "azurerm" {
  #   resource_group_name  = "gps-tfstate-rg"
  #   storage_account_name = "gpstfstate"
  #   container_name       = "tfstate"
  #   key                  = "gps.terraform.tfstate"
  # }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
  }
}
